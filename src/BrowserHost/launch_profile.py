"""CloakBrowser profile launcher (browser_vault) with a real CDP debug port.

Chosen mechanism: **direct subprocess launch** of the stealth Chromium binary
resolved by the CloakBrowser SDK - NOT the SDK's own ``launch()`` helpers.

Why (verified against the installed cloakbrowser 0.6.3 and playwright 1.62.0):

1. The SDK's ``launch`` / ``launch_persistent_context`` are thin wrappers over
   ``playwright.chromium.launch*`` (see ``cloakbrowser/browser.py``).
2. Playwright's driver *always* pushes ``--remote-debugging-pipe`` into the
   Chromium argv (driver bundle: ``chromeArguments.push("--remote-debugging-pipe")``)
   and rejects caller-supplied pipe/CDP flags; cloakbrowser additionally
   hardcodes ``ignore_default_args``, so that default cannot be removed.
3. Chromium ignores ``--remote-debugging-port`` whenever the pipe handler is
   active, so an SDK-launched browser can never expose
   ``http://127.0.0.1:4022`` for browser-harness / Playwright
   ``connect_over_cdp`` to attach.
4. cloakbrowser itself already runs the binary via plain subprocess for its
   ``--version`` probe, and exposes ``ensure_binary()`` / ``build_args()`` /
   ``build_launch_env()`` - a subprocess launch reuses the exact same binary,
   stealth flags and license env injection while keeping full control of argv.

So the fallback the task reserved for "SDK does not support
--remote-debugging-port" is in fact the ONLY workable mechanism, and it is
implemented here as the primary one. The SDK is still used, for all it does
well: ``ensure_binary()`` (locate/download the stealth Chromium),
``build_args()`` (stealth fingerprint flags, dedup, timezone/locale flags) and
``build_launch_env()`` (Pro license key injection for the child process).

Behaviour:

    * headless=False, always (per AGENTS.md: CDP tools attach to a headed
      browser; headed also keeps the fingerprint surface natural).
    * ``--fingerprint=<seed>`` comes from ``browser_vault/<profile>/config.json``;
      the seed is generated once at profile creation and must never change on
      a profile that is in use. (CloakBrowser's own ``.cloakbrowser-seed``
      file lives in a 5-digit range and is deliberately NOT used here -
      config.json is the single source of truth; passing ``--fingerprint``
      explicitly also keeps the SDK from managing its own seed file.)
    * ``extra_flags`` from config.json (e.g. the WebRTC leak guard
      ``--webrtc-ip-handling-policy=disable_non_proxied_udp``) are appended
      after the stealth defaults; later values win on duplicate flag keys.
    * ``--remote-allow-origins=*`` is added so external CDP clients can attach
      on recent Chromium builds (origin checks on the WebSocket upgrade).
    * Chrome-warning switches are STRIPPED from the final argv: the SDK's
      ``build_args()`` adds ``--no-sandbox`` by default (CI-friendly), which
      makes Chromium show the "unsupported command-line flag ... Stability and
      security will suffer" infobar - a security downgrade and an automation
      tell. On a real Windows desktop the sandbox stays enabled.
    * The process is spawned detached from Playwright: closing this launcher
      never closes the browser.

Usage:
    python src/BrowserHost/launch_profile.py --profile flow_main --wait
    python src/BrowserHost/launch_profile.py --profile flow_main --dry-run

``--dry-run`` prints the exact binary, argv, env-injection note and CDP URL
without starting anything (and without ever triggering a binary download).
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAULT_DIR = PROJECT_ROOT / "browser_vault"
TEMPLATE_PATH = VAULT_DIR / "_template" / "config.json"
PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Used only when _template/config.json is missing; keep in sync with the file.
FALLBACK_TEMPLATE: dict[str, Any] = {
    "profile_id": "_template",
    "fingerprint_seed": 42815193,
    "platform": "windows",
    "timezone_id": "Asia/Ho_Chi_Minh",
    "locale": "en-US",
    "proxy": None,
    "extra_flags": ["--webrtc-ip-handling-policy=disable_non_proxied_udp"],
}

MAX_SEED = 2**31 - 1


def generate_seed() -> int:
    """Fresh 8-digit fingerprint seed (project convention: generated once)."""
    return random.SystemRandom().randint(10_000_000, 99_999_999)


def load_or_create_profile(profile_id: str, vault_dir: Path) -> tuple[dict[str, Any], bool, Path]:
    """Load browser_vault/<id>/config.json; create it from _template if absent.

    The template's example seed is NEVER reused for real profiles - each
    profile gets its own freshly generated seed, because a shared seed would
    give every profile the same fingerprint identity.
    """
    if not PROFILE_ID_RE.match(profile_id) or profile_id == "_template":
        raise SystemExit(f"[launch] invalid profile id: {profile_id!r} (allowed: [A-Za-z0-9][A-Za-z0-9._-]*)")
    profile_dir = vault_dir / profile_id
    cfg_path = profile_dir / "config.json"
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8")), False, cfg_path

    template = (
        json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        if TEMPLATE_PATH.is_file()
        else copy.deepcopy(FALLBACK_TEMPLATE)
    )
    cfg = copy.deepcopy(template)
    cfg["profile_id"] = profile_id
    cfg["fingerprint_seed"] = generate_seed()
    profile_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cfg, True, cfg_path


def validate_and_repair(cfg: dict[str, Any], cfg_path: Path, profile_id: str) -> None:
    """Sanity-check config fields; repair a missing/invalid seed in place."""
    seed = cfg.get("fingerprint_seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or not (1 <= seed <= MAX_SEED):
        cfg["fingerprint_seed"] = generate_seed()
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[launch] !! fingerprint_seed missing/invalid - regenerated once: {cfg['fingerprint_seed']}")

    if cfg.get("platform") != "windows" and sys.platform == "win32":
        print(
            f"[launch] !! config platform={cfg.get('platform')!r} does not match the real OS "
            "(windows); fingerprints may leak a mismatch (see AGENTS.md)."
        )
    extra_flags = cfg.get("extra_flags")
    if extra_flags is not None and not (isinstance(extra_flags, list) and all(isinstance(f, str) for f in extra_flags)):
        raise SystemExit(f"[launch] config {cfg_path}: extra_flags must be a list of strings")
    proxy = cfg.get("proxy")
    if proxy is not None:
        try:
            normalize_proxy(proxy)
        except ValueError as exc:
            raise SystemExit(f"[launch] config {cfg_path}: {exc}") from exc
    bypass = cfg.get("proxy_bypass")
    if bypass is not None and not (isinstance(bypass, (str, list))):
        raise SystemExit(f"[launch] config {cfg_path}: proxy_bypass must be a string or list of strings")

    if cfg.get("profile_id") != profile_id:
        print(f"[launch] !! config profile_id={cfg.get('profile_id')!r} != directory {profile_id!r}")


PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")
DEFAULT_PROXY_SCHEME = "http"


def _split_proxy_string(raw: str) -> dict[str, str]:
    """Parse ``host:port`` / ``user:pass@host:port`` / ``scheme://...`` into parts."""
    text = raw.strip()
    candidate = text if "://" in text else f"{DEFAULT_PROXY_SCHEME}://{text}"
    try:
        parts = urlsplit(candidate)
        port = parts.port
    except ValueError as exc:  # malformed port / IPv6 literal
        raise ValueError(f"proxy không hợp lệ ({raw!r}): {exc}") from exc

    scheme = (parts.scheme or DEFAULT_PROXY_SCHEME).lower()
    if scheme not in PROXY_SCHEMES:
        raise ValueError(
            f"proxy scheme {scheme!r} không hỗ trợ (chỉ {', '.join(PROXY_SCHEMES)})"
        )
    host = parts.hostname
    if not host:
        raise ValueError(f"proxy thiếu host ({raw!r})")
    if not port:
        raise ValueError(f"proxy thiếu port ({raw!r}), ví dụ host:port")

    out = {"scheme": scheme, "host": host, "port": str(port)}
    if parts.username:
        out["username"] = unquote(parts.username)
    if parts.password:
        out["password"] = unquote(parts.password)
    return out


def normalize_proxy(proxy: Any) -> Optional[dict[str, str]]:
    """Normalize any accepted proxy shape; ``None`` means "direct IP".

    Accepted inputs (all optional — empty values fall back to direct):
      * ``None`` / ``""`` / ``"   "``            → direct connection
      * ``"http://user:pass@host:port"``          → full URL
      * ``"user:pass@host:port"``                 → schemeless, http assumed
      * ``"host:port"`` / ``"socks5://host:port"``
      * ``{"server": ..., "username": ..., "password": ...}``
    """
    if proxy is None:
        return None
    if isinstance(proxy, str):
        if not proxy.strip():
            return None
        return _split_proxy_string(proxy)
    if isinstance(proxy, dict):
        server = str(proxy.get("server") or proxy.get("url") or "").strip()
        username = proxy.get("username")
        password = proxy.get("password")
        if not server:
            return None
        if "://" not in server:
            server = f"{proxy.get('scheme') or DEFAULT_PROXY_SCHEME}://{server}"
        if username and "://" in server:
            scheme, rest = server.split("://", 1)
            cred = quote(str(username), safe="")
            if password:
                cred += ":" + quote(str(password), safe="")
            server = f"{scheme}://{cred}@{rest}"
        return _split_proxy_string(server)
    raise ValueError(f"proxy phải là null, chuỗi URL hoặc object (nhận {type(proxy).__name__})")


def proxy_to_url(proxy: Any) -> str:
    """Normalize a config proxy into a ``--proxy-server`` URL (empty = direct).

    Inline credentials in the URL are accepted by this binary generation
    (windows-x64 >= 146.0.7680.177.5, see cloakbrowser config
    HTTP_PROXY_INLINE_AUTH_MIN_VERSION), so user:pass is inlined safely.
    """
    parts = normalize_proxy(proxy)
    if parts is None:
        return ""
    host = f"[{parts['host']}]" if ":" in parts["host"] else parts["host"]
    cred = ""
    if parts.get("username"):
        cred = quote(parts["username"], safe="")
        if parts.get("password"):
            cred += ":" + quote(parts["password"], safe="")
        cred += "@"
    return f"{parts['scheme']}://{cred}{host}:{parts['port']}"


def describe_proxy(proxy: Any) -> str:
    """Credential-free proxy label for logs (never print passwords)."""
    parts = normalize_proxy(proxy)
    if parts is None:
        return "direct (không proxy)"
    host = f"[{parts['host']}]" if ":" in parts["host"] else parts["host"]
    who = f"{parts['username']}@" if parts.get("username") else ""
    return f"{parts['scheme']}://{who}{host}:{parts['port']}"


# Switches that make Chromium show the "unsupported command-line flag -
# Stability and security will suffer" infobar (bad_flags_prompt.cc list).
# The cloakbrowser SDK adds --no-sandbox by default; on a real Windows desktop
# it is unnecessary, so these are stripped from the final argv.
WARNING_FLAGS = {
    "--no-sandbox",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--ignore-certificate-errors",
    "--disable-site-isolation-trials",
}


def strip_warning_flags(args: list[str]) -> list[str]:
    """Drop Chromium switches that trigger the unsupported-flags infobar."""
    kept: list[str] = []
    for item in args:
        if item.split("=", 1)[0] in WARNING_FLAGS:
            print(f"[launch] stripped banner flag: {item!r} "
                  "(avoids the 'unsupported command-line flag' infobar)")
            continue
        kept.append(item)
    return kept


def build_command(cfg: dict[str, Any], binary_path: str, user_data_dir: Path, port: int, url: Optional[str] = None) -> list[str]:
    """Assemble the full Chromium argv: SDK stealth flags + CDP/session flags."""
    import cloakbrowser  # lazy: --help must work even without the package

    extra: list[str] = [str(flag) for flag in (cfg.get("extra_flags") or [])]
    # Identity/session/CDP flags come last: on duplicate flag keys, later wins.
    extra.append(f"--fingerprint={cfg['fingerprint_seed']}")
    extra.append(f"--user-data-dir={user_data_dir}")
    extra.append(f"--remote-debugging-port={port}")
    extra.append("--remote-allow-origins=*")
    proxy_url = proxy_to_url(cfg.get("proxy"))
    if proxy_url:
        # Per-browser proxy (Task 2). Empty/absent proxy ⇒ direct IP, no flag.
        extra.append(f"--proxy-server={proxy_url}")
        bypass = cfg.get("proxy_bypass")
        if bypass:
            joined = bypass if isinstance(bypass, str) else ",".join(str(b) for b in bypass)
            if joined.strip():
                extra.append(f"--proxy-bypass-list={joined}")


    args = cloakbrowser.build_args(
        True,
        extra,
        timezone=cfg.get("timezone_id"),
        locale=cfg.get("locale"),
        headless=False,  # headed: CDP tools need it and headed avoids headless tells
        start_maximized=True,
    )
    if "--new-window" not in args:
        args.append("--new-window")
    cmd = [binary_path, *strip_warning_flags(args)]
    if url:
        cmd.append(url)
    return cmd


def describe_binary() -> tuple[str, bool]:
    """Path + installed flag WITHOUT triggering a download (used by --dry-run)."""
    import cloakbrowser

    info = cloakbrowser.binary_info()
    return str(info["binary_path"]), bool(info["installed"])


def resolve_binary() -> str:
    """Ensure the stealth Chromium exists (downloads/updates if needed)."""
    import cloakbrowser

    return str(cloakbrowser.ensure_binary())


def build_child_env() -> Optional[dict[str, str]]:
    """Child env with Pro license injection when needed; None = inherit parent."""
    try:
        from cloakbrowser.license import build_launch_env, resolve_license_key

        return build_launch_env(resolve_license_key(None))
    except Exception as exc:  # noqa: BLE001 - license env is best-effort for the free tier
        print(f"[launch] license env skipped: {exc}", file=sys.stderr)
        return None


def wait_for_cdp(port: int, timeout_s: float) -> int:
    """Poll the CDP HTTP endpoint until the browser under it is responsive."""
    import requests

    url = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + timeout_s
    last_error: Optional[str] = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1.0)
            if response.status_code == 200:
                payload = response.json()
                print(f"[launch] browser ready  : {payload.get('Browser', '(unknown)')}")
                print(f"[launch] CDP json/version: {url}")
                print(f"[launch] webSocketDebuggerUrl: {payload.get('webSocketDebuggerUrl')}")
                return 0
        except Exception as exc:  # noqa: BLE001 - keep polling until timeout
            last_error = str(exc)
        time.sleep(0.5)
    print(f"[launch] !! CDP endpoint not ready after {timeout_s}s (last error: {last_error})", file=sys.stderr)
    return 3


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a CloakBrowser profile from browser_vault with CDP port 4022.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--profile", required=True, help="Profile id under browser_vault/ (created from _template on first use)")
    parser.add_argument("--port", type=int, default=4022, help="Remote debugging (CDP) port; discovery tools attach here")
    parser.add_argument("--wait", action="store_true", help="Poll /json/version until the browser answers (recommended before attaching tools)")
    parser.add_argument("--wait-timeout", type=float, default=30.0, help="Seconds to wait with --wait")
    parser.add_argument("--dry-run", action="store_true", help="Print the exact command without starting the browser")
    parser.add_argument("--vault-dir", default=None, help="Override the browser_vault location (testing/advanced)")
    parser.add_argument(
        "--pid-file",
        default=None,
        help="Write the launched browser PID to this file (used by pool_supervisor to hibernate the account later)",
    )
    parser.add_argument(
        "--url",
        default="https://flow.google.com/",
        help="Initial URL to navigate to (defaults to https://flow.google.com/)",
    )
    return parser.parse_args(argv)


if sys.platform == "win32":
    import ctypes
    import os
    from ctypes import wintypes

    class _STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_char_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    def _spawn_detached_win32(
        command: list[str],
        env: Optional[dict[str, str]] = None,
        desktop: str = r"winsta0\default",
    ) -> int:
        cmd_str = subprocess.list2cmdline(command)
        si = _STARTUPINFOW()
        si.cb = ctypes.sizeof(_STARTUPINFOW)
        si.lpDesktop = desktop
        si.dwFlags = 0x00000001  # STARTF_USESHOWWINDOW
        si.wShowWindow = 3       # SW_SHOWMAXIMIZED
        pi = _PROCESS_INFORMATION()

        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        env_block = None
        if env is not None:
            flags |= 0x00000400  # CREATE_UNICODE_ENVIRONMENT
            full_env = dict(os.environ)
            full_env.update(env)
            env_str = "".join(f"{k}={full_env[k]}\0" for k in sorted(full_env.keys())) + "\0"
            env_block = ctypes.c_wchar_p(env_str)

        res = ctypes.windll.kernel32.CreateProcessW(
            None, cmd_str, None, None, False, flags, env_block, None, ctypes.byref(si), ctypes.byref(pi)
        )
        if not res and desktop:
            si.lpDesktop = None
            res = ctypes.windll.kernel32.CreateProcessW(
                None, cmd_str, None, None, False, flags, env_block, None, ctypes.byref(si), ctypes.byref(pi)
            )
        if not res:
            err = ctypes.GetLastError()
            raise OSError(f"CreateProcessW failed with error {err}")

        pid = int(pi.dwProcessId)
        ctypes.windll.kernel32.CloseHandle(pi.hProcess)
        ctypes.windll.kernel32.CloseHandle(pi.hThread)
        return pid


def profile_browser_pid(user_data_dir: Path) -> Optional[int]:
    """PID của browser đang sống với *chính* `user_data_dir` này, nếu có.

    Chromium không cho hai tiến trình chia sẻ một `--user-data-dir`. Nếu profile đã có
    browser sống, lần launch sau sẽ không mở cửa sổ mới: Chromium chuyển tiếp URL sang
    tiến trình cũ và **mở thêm một tab** rồi thoát ngay. Đó chính là cách 8 tab
    `flow.google.com` xuất hiện trong một cửa sổ duy nhất (đo 2026‑11‑12: 1 browser,
    8 tab, 1.6 GB RAM) — mỗi lần `run.ps1 start` hay restart khi browser còn sống là một tab.

    Trả về PID để `main()` báo cho người dùng thay vì cộng thêm tab.
    """
    try:
        import psutil  # có sẵn trong .venv; thiếu thì bỏ qua guard, không chặn launch
    except ImportError:
        return None

    target = str(user_data_dir).lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if not (proc.info["name"] or "").lower().startswith("chrome"):
                continue
            cmdline = [str(a) for a in (proc.info["cmdline"] or ())]
            # Renderer/utility/gpu mang cùng `--user-data-dir` như tiến trình cha. Nếu không
            # loại ra, guard trả về PID của một renderer — ghi vào browser.pid thì `stop`
            # chỉ giết đứa con, browser cha vẫn sống.
            if any(a.startswith("--type=") for a in cmdline):
                continue
            for arg in cmdline:
                if arg.lower().startswith("--user-data-dir="):
                    if arg.split("=", 1)[1].lower() == target:
                        return proc.info["pid"]
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def spawn_browser_process(command: list[str], env: Optional[dict[str, str]] = None) -> int:
    """Launch the browser detached from the launcher process.

    On Windows, uses CreateProcessW with lpDesktop='winsta0\\default' so the
    window appears on the user's interactive desktop, not in a hidden sandbox desktop.
    """
    if sys.platform == "win32":
        return _spawn_detached_win32(command, env=env)

    proc = subprocess.Popen(
        command,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    args = parse_args(argv)
    vault_dir = Path(args.vault_dir).resolve() if args.vault_dir else VAULT_DIR

    cfg, created, cfg_path = load_or_create_profile(args.profile, vault_dir)
    if created:
        print(f"[launch] created new profile config: {cfg_path}")
        print("[launch]   - fingerprint_seed was generated ONCE for this profile; do not change it while in use")
        print("[launch]   - review proxy/locale/timezone/extra_flags in the file if needed")
    validate_and_repair(cfg, cfg_path, args.profile)

    user_data_dir = cfg_path.parent / "user_data"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.dry_run:
            binary_path, installed = describe_binary()
        else:
            binary_path = resolve_binary()
            installed = True
    except ImportError:
        print("[launch] !! cloakbrowser is not installed in this Python environment", file=sys.stderr)
        return 2

    command = build_command(cfg, binary_path, user_data_dir, args.port, url=args.url)

    print(f"[launch] profile      : {args.profile}")
    print(f"[launch] platform     : {cfg.get('platform')} | timezone: {cfg.get('timezone_id')} | locale: {cfg.get('locale')}")
    print(f"[launch] seed         : {cfg['fingerprint_seed']}")
    print(f"[launch] proxy        : {describe_proxy(cfg.get('proxy'))}")

    print(f"[launch] user_data_dir: {user_data_dir}")
    print(f"[launch] CDP port     : {args.port}")

    if args.dry_run:
        print(f"[launch] binary       : {binary_path}" + ("" if installed else "  (NOT installed - a real run would download it first)"))
        print("[launch] --dry-run: nothing was started. Command that would run:")
        print("  (argv, one element per line)")
        for item in command:
            print(f"    {item}")
        print("  (single line, Windows-quoted)")
        print("    " + subprocess.list2cmdline(command))
        env = build_child_env()
        print(f"  env      : {'inherit parent (free tier)' if env is None else 'child env with license key injection'}")
        return 0

    env = build_child_env()

    # Profile đã có browser sống ⇒ đừng spawn thêm. Chromium sẽ chuyển URL sang cửa sổ cũ
    # và mở một tab mới rồi thoát, nên "khởi động lại" chỉ làm phình tab chứ không khởi động
    # lại gì cả. Xem `profile_browser_pid`.
    existing = profile_browser_pid(user_data_dir)
    if existing:
        print(
            f"[launch] !! profile '{args.profile}' đã có browser đang chạy (pid={existing}). "
            "Không spawn thêm — Chromium chỉ mở thêm một tab trong cửa sổ đó.",
            file=sys.stderr,
        )
        print(
            "[launch]    Muốn khởi động lại thật: dừng browser trước "
            "(``.\\run.ps1 stop``) rồi start lại.",
            file=sys.stderr,
        )
        if args.pid_file:
            try:
                Path(args.pid_file).write_text(str(existing), encoding="ascii")
            except OSError:
                pass
        # Exit 0, không phải lỗi: trạng thái mong muốn (browser sống cho profile này) đã đạt.
        # `run.ps1` coi exit != 0 là "khởi động thất bại" và ném lỗi, trong khi đây là no-op
        # đúng ý — người dùng chỉ cần browser sẵn sàng để attach CDP.
        return 0

    try:
        pid = spawn_browser_process(command, env=env)
    except OSError as exc:
        print(f"[launch] !! failed to start browser: {exc}", file=sys.stderr)
        return 2

    print(f"[launch] started      : pid={pid}")
    print(f"[launch] CDP endpoint : http://127.0.0.1:{args.port}")
    if args.pid_file:
        try:
            pid_path = Path(args.pid_file)
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text(str(pid), encoding="utf-8")
            print(f"[launch] pid file     : {pid_path}")
        except OSError as exc:
            print(f"[launch] !! could not write pid file {args.pid_file!r}: {exc}", file=sys.stderr)
    if args.wait:
        return wait_for_cdp(args.port, args.wait_timeout)
    print("[launch] (browser keeps running after this script exits; attach tools to the CDP endpoint)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
