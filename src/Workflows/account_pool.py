"""AccountPoolManager — Dynamic N-Account pool with demand-based allocation.

Implements docs/upgrade_plan_n_account_pool.md (Phần 1–2, Task 3):

    N_alloc(J) = min(N, M_RAM, max(1, ceil(J / Q_target)))

    * N       — tài khoản khả dụng (quét ``browser_vault/`` hoặc đọc
                ``configs/accounts_pool.json``; fallback ``flow_main``).
    * Q_target— ``target_jobs_per_account`` (mặc định 25 ảnh/account).
    * M_RAM   — ``max_active_browsers`` (trần browser mở song song).
    * Số còn lại giữ STANDBY — không đánh thức browser nếu không cần.

Selection (wear-leveling + sticky reference affinity, plan §1.3 / Phần 2):

    1. Ưu tiên account đã có ``media_id``/template cho ảnh tham chiếu của batch.
    2. Sau đó ưu tiên account ít dùng nhất (total_completed thấp, last_used_at cũ).

Hot-spare failover: khi một account dính 429/401/403 hoặc breaker mở, worker
dừng account đó và ``promote_standby()`` rút một account dự phòng vào thế chỗ.

Runtime state (counters, cooldown, last batch) lưu tại ``out/pool_state.json``
(gitignored); cache tham chiếu i2i lưu tại ``configs/reference_media_cache.json``.
"""

from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit

from ..BrowserHost.pool_supervisor import PoolSupervisor
from .flow_client import CircuitBreaker, FlowClient, sha256_file

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "configs" / "accounts_pool.json"
DEFAULT_STATE_PATH = ROOT / "out" / "pool_state.json"
DEFAULT_BREAKER_DIR = ROOT / "out" / "breakers"
DEFAULT_REF_CACHE_PATH = ROOT / "configs" / "reference_media_cache.json"
DEFAULT_OUT_ROOT = ROOT / "out" / "playground"
DEFAULT_VAULT_DIR = ROOT / "browser_vault"
DEFAULT_PID_DIR = ROOT / "out" / "pids"

Q_TARGET_DEFAULT = 25
MAX_RAM_DEFAULT = 4
PORT_BASE_DEFAULT = 9222


class PoolUnavailableError(RuntimeError):
    """No healthy account is available for a job (all cooldown/disabled/failed)."""


# --------------------------------------------------------------------------- #
# Config / state carriers
# --------------------------------------------------------------------------- #


@dataclass
class AccountConfig:
    id: str
    profile_id: str
    cdp_port: int
    enabled: bool = True
    note: str = ""


@dataclass
class ActiveAccount:
    """An account whose browser is confirmed up (or externally managed)."""

    config: AccountConfig
    cdp_url: str


def _default_account_state() -> dict:
    return {
        "total_completed": 0,   # ảnh được Google nhận (≈ credit đã dùng)
        "total_rejected": 0,    # bị từ chối (0 credit)
        "total_failed": 0,      # lỗi kỹ thuật của ta
        "last_used_at_ms": 0,
        "last_error": None,
        "last_error_ms": 0,
        "last_woken_at_ms": 0,
    }


# --------------------------------------------------------------------------- #
# Reference media registry (i2i template cache, plan Phần 2)
# --------------------------------------------------------------------------- #


class ReferenceMediaRegistry:
    """Cache ``account_id -> sha256(file) -> ReferenceTemplate``.

    ``media_id`` thật chỉ tồn tại trong project của từng account, nên cache
    được khoá theo account. Ngoài media_id (best-effort), registry lưu luôn
    ``template_args`` — layout request i2i do chính app dựng khi ta đính ảnh
    tham chiếu (xem flow_client.upload_reference_image) — để các shot sau chỉ
    cần capture token mới rồi replay, không phải upload lại.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_REF_CACHE_PATH
        self._lock = threading.RLock()
        self.data: dict = {"version": 1, "accounts": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("accounts"), dict):
                    self.data = raw
        except Exception:  # noqa: BLE001
            self.data = {"version": 1, "accounts": {}}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -- API ---------------------------------------------------------------- #

    def get(self, account_id: str, sha: str) -> Optional[dict]:
        with self._lock:
            return (self.data.get("accounts", {}).get(account_id) or {}).get(sha)

    def put(self, account_id: str, template: dict) -> None:
        sha = str(template.get("sha256") or "")
        if not sha:
            return
        with self._lock:
            self.data.setdefault("accounts", {}).setdefault(account_id, {})[sha] = template
            self._save()

    def has(self, account_id: str, sha: str) -> bool:
        return self.get(account_id, sha) is not None

    def count_for(self, account_id: str, shas: Iterable[str]) -> int:
        bucket = self.data.get("accounts", {}).get(account_id) or {}
        return sum(1 for s in shas if s in bucket)

    def stats(self) -> dict:
        with self._lock:
            accounts = self.data.get("accounts", {})
            return {
                "accounts": len(accounts),
                "entries": sum(len(v) for v in accounts.values() if isinstance(v, dict)),
            }


# --------------------------------------------------------------------------- #
# AccountPoolManager
# --------------------------------------------------------------------------- #


class AccountPoolManager:
    """Owns account discovery, allocation, working-set launch and failover."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
        breaker_dir: Optional[Path] = None,
        ref_cache_path: Optional[Path] = None,
        vault_dir: Optional[Path] = None,
        out_root: Optional[Path] = None,
        supervisor: Optional[PoolSupervisor] = None,
        default_cdp_url: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        self.breaker_dir = Path(breaker_dir) if breaker_dir else DEFAULT_BREAKER_DIR
        self.out_root = Path(out_root) if out_root else DEFAULT_OUT_ROOT
        self.vault_dir = Path(vault_dir) if vault_dir else DEFAULT_VAULT_DIR
        self._log = log or (lambda *_: None)

        self.supervisor = supervisor or PoolSupervisor(vault_dir=self.vault_dir, pid_dir=DEFAULT_PID_DIR, log=self._log)
        self.registry = ReferenceMediaRegistry(ref_cache_path)

        self._lock = threading.RLock()
        self.accounts: list[AccountConfig] = []
        self.target_jobs_per_account = Q_TARGET_DEFAULT
        self.max_active_browsers = MAX_RAM_DEFAULT
        self.port_base = PORT_BASE_DEFAULT
        self.auto_discover = True
        self._explicit_accounts = False

        self._state: dict = {"accounts": {}, "last_batch": None}
        self._current_batch: Optional[dict] = None
        self._clients: dict[str, FlowClient] = {}

        self._load_config(default_cdp_url=default_cdp_url)
        self._load_state()

    # ------------------------------------------------------------------ #
    # Config
    # ------------------------------------------------------------------ #

    def _load_config(self, default_cdp_url: Optional[str] = None) -> None:
        raw: dict = {}
        try:
            if self.config_path.exists():
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raw = {}
        except Exception as exc:  # noqa: BLE001
            self._log(f"[pool] config lỗi ({exc}) — dùng mặc định")

        self.target_jobs_per_account = int(raw.get("target_jobs_per_account") or Q_TARGET_DEFAULT)
        self.max_active_browsers = int(raw.get("max_active_browsers") or MAX_RAM_DEFAULT)
        self.port_base = int(raw.get("port_base") or PORT_BASE_DEFAULT)
        self.auto_discover = bool(raw.get("auto_discover", True))

        accounts: list[AccountConfig] = []
        for a in raw.get("accounts") or []:
            if not isinstance(a, dict) or not a.get("id"):
                continue
            aid = str(a["id"])
            accounts.append(AccountConfig(
                id=aid,
                profile_id=str(a.get("profile_id") or aid),
                cdp_port=int(a.get("cdp_port") or (self.port_base + len(accounts))),
                enabled=bool(a.get("enabled", True)),
                note=str(a.get("note") or ""),
            ))
        self._explicit_accounts = bool(accounts)

        if not accounts and self.auto_discover:
            accounts = self.discover_accounts()

        if not accounts:
            # Backward compatibility: no vault/config yet → single synthetic
            # account on the default CDP URL, exactly like pre-pool behaviour.
            port = PORT_BASE_DEFAULT
            if default_cdp_url:
                parsed = urlsplit(default_cdp_url if "://" in default_cdp_url else "http://" + default_cdp_url)
                port = int(parsed.port or PORT_BASE_DEFAULT)
            accounts = [AccountConfig(id="flow_main", profile_id="flow_main", cdp_port=port, note="fallback")]

        if default_cdp_url and not self._explicit_accounts and accounts:
            # --cdp-url semantics kept for the single-account flow: bind the
            # first (usually only) account to the URL the operator passed in.
            parsed = urlsplit(default_cdp_url if "://" in default_cdp_url else "http://" + default_cdp_url)
            accounts[0].cdp_port = int(parsed.port or PORT_BASE_DEFAULT)

        self.accounts = accounts
        self._log(f"[pool] N={len(accounts)} account(s): " + ", ".join(f"{a.id}:{a.cdp_port}" for a in accounts))

    def discover_accounts(self) -> list[AccountConfig]:
        """Scan browser_vault/ for profile dirs (port = port_base + index)."""
        out: list[AccountConfig] = []
        try:
            if self.vault_dir.exists():
                for d in sorted(self.vault_dir.iterdir()):
                    if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
                        continue
                    out.append(AccountConfig(
                        id=d.name, profile_id=d.name, cdp_port=self.port_base + len(out),
                    ))
        except OSError as exc:  # noqa: BLE001
            self._log(f"[pool] không quét được browser_vault: {exc}")
        return out

    def _save_config(self) -> None:
        raw: dict = {}
        try:
            if self.config_path.exists():
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raw = {}
        except Exception:  # noqa: BLE001
            raw = {}
        raw["target_jobs_per_account"] = self.target_jobs_per_account
        raw["max_active_browsers"] = self.max_active_browsers
        raw.setdefault("port_base", self.port_base)
        raw.setdefault("auto_discover", self.auto_discover)
        if self._explicit_accounts:
            raw["accounts"] = [
                {"id": a.id, "profile_id": a.profile_id, "cdp_port": a.cdp_port,
                 "enabled": a.enabled, **({"note": a.note} if a.note else {})}
                for a in self.accounts
            ]
        else:
            raw.setdefault("accounts", [])
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:  # noqa: BLE001
            self._log(f"[pool] không ghi được config: {exc}")

    def update_config(self, target_jobs_per_account: Optional[int] = None,
                      max_active_browsers: Optional[int] = None) -> dict:
        """Persist tuning knobs (UI chỉnh ``target_jobs_per_account``)."""
        with self._lock:
            if target_jobs_per_account is not None:
                q = int(target_jobs_per_account)
                if not (1 <= q <= 500):
                    raise ValueError("target_jobs_per_account phải trong 1..500")
                self.target_jobs_per_account = q
            if max_active_browsers is not None:
                m = int(max_active_browsers)
                if not (1 <= m <= 16):
                    raise ValueError("max_active_browsers phải trong 1..16")
                self.max_active_browsers = m

            self._save_config()
            return {
                "target_jobs_per_account": self.target_jobs_per_account,
                "max_active_browsers": self.max_active_browsers,
            }

    def next_suggested_port(self) -> int:
        """Find the lowest available CDP port starting from port_base."""
        with self._lock:
            used = {a.cdp_port for a in self.accounts}
            p = self.port_base
            while p in used:
                p += 1
            return p

    def add_account(
        self,
        account_id: str,
        profile_id: Optional[str] = None,
        cdp_port: Optional[int] = None,
        enabled: bool = True,
        note: str = "",
        create_profile: bool = True,
    ) -> AccountConfig:
        """Add a new account/profile to the pool, optionally creating the vault profile."""
        from ..BrowserHost.launch_profile import PROFILE_ID_RE, load_or_create_profile

        aid = str(account_id or "").strip()
        if not PROFILE_ID_RE.match(aid) or aid == "_template":
            raise ValueError(f"ID account không hợp lệ: {aid!r} (chỉ dùng chữ, số, dấu gạch)")

        pid = str(profile_id or aid).strip()
        if not PROFILE_ID_RE.match(pid) or pid == "_template":
            raise ValueError(f"Profile ID không hợp lệ: {pid!r}")

        with self._lock:
            if any(a.id == aid for a in self.accounts):
                raise ValueError(f"Account ID {aid!r} đã tồn tại trong pool")

            if cdp_port is None or int(cdp_port) <= 0:
                port = self.next_suggested_port()
            else:
                port = int(cdp_port)
                if any(a.cdp_port == port for a in self.accounts):
                    raise ValueError(f"Cổng CDP :{port} đã được dùng bởi account khác")

            if create_profile:
                load_or_create_profile(pid, self.vault_dir)

            acc = AccountConfig(
                id=aid,
                profile_id=pid,
                cdp_port=port,
                enabled=bool(enabled),
                note=str(note or ""),
            )
            self.accounts.append(acc)
            self._explicit_accounts = True
            self._save_config()
            self._save_state()
            self._log(f"[pool] Đã thêm account mới: {aid} (profile={pid}, cdp_port={port})")
            return acc

    def update_account(
        self,
        account_id: str,
        enabled: Optional[bool] = None,
        note: Optional[str] = None,
        cdp_port: Optional[int] = None,
    ) -> AccountConfig:
        """Update an existing account's status, note, or CDP port."""
        with self._lock:
            acc = self._account(account_id)
            if acc is None:
                raise KeyError(f"Account không tồn tại: {account_id}")

            if cdp_port is not None:
                new_port = int(cdp_port)
                if new_port != acc.cdp_port and any(a.cdp_port == new_port and a.id != account_id for a in self.accounts):
                    raise ValueError(f"Cổng CDP :{new_port} đã được dùng bởi account khác")
                acc.cdp_port = new_port

            if enabled is not None:
                acc.enabled = bool(enabled)
            if note is not None:
                acc.note = str(note)

            self._explicit_accounts = True
            self._save_config()
            self._log(f"[pool] Đã cập nhật account: {account_id}")
            return acc

    def remove_account(self, account_id: str, delete_vault: bool = False) -> dict:
        """Remove an account from the pool, optionally deleting its browser_vault directory."""
        import shutil

        with self._lock:
            acc = self._account(account_id)
            if acc is None:
                raise KeyError(f"Account không tồn tại: {account_id}")

            try:
                self.hibernate_account(account_id)
            except Exception:
                pass

            self.accounts = [a for a in self.accounts if a.id != account_id]
            self._clients.pop(account_id, None)
            if account_id in self._state.get("accounts", {}):
                self._state["accounts"].pop(account_id, None)

            if delete_vault:
                p_dir = self.vault_dir / acc.profile_id
                if p_dir.exists() and p_dir.is_dir() and acc.profile_id != "_template":
                    shutil.rmtree(p_dir, ignore_errors=True)

            self._explicit_accounts = True
            self._save_config()
            self._save_state()
            self._log(f"[pool] Đã xóa account: {account_id} (delete_vault={delete_vault})")
            return {"ok": True, "removed": account_id}

    def account_detail(self, account_id: str) -> dict:
        """Probe an account's live CDP and Flow session status."""
        a = self._account(account_id)
        if a is None:
            raise KeyError(f"Account không tồn tại: {account_id}")

        alive = self.supervisor.is_alive(a.cdp_port, 1.0)
        flow_status = None
        if alive:
            try:
                cl = self.client_for(account_id)
                st = cl.status()
                flow_status = st.model_dump()
            except Exception as exc:  # noqa: BLE001
                flow_status = {"error": str(exc)}

        st = self._account_state(account_id)
        return {
            "account": {
                "id": a.id,
                "profile_id": a.profile_id,
                "cdp_port": a.cdp_port,
                "cdp_url": self.supervisor.cdp_url(a.cdp_port),
                "enabled": a.enabled,
                "note": a.note,
                "running": alive,
                "managed": self.supervisor.is_managed(a.profile_id),
                "status": "disabled" if not a.enabled else ("cooldown" if self.cooldown_remaining_s(a.id) > 0 else "ready"),
                "total_completed": int(st.get("total_completed") or 0),
                "total_rejected": int(st.get("total_rejected") or 0),
                "total_failed": int(st.get("total_failed") or 0),
            },
            "flow": flow_status,
        }

    # ------------------------------------------------------------------ #
    # Runtime state
    # ------------------------------------------------------------------ #

    def _load_state(self) -> None:
        try:
            if self.state_path.exists():
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._state = {
                        "accounts": raw.get("accounts") if isinstance(raw.get("accounts"), dict) else {},
                        "last_batch": raw.get("last_batch"),
                    }
        except Exception:  # noqa: BLE001
            pass

    def _save_state(self) -> None:
        with self._lock:
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=1), encoding="utf-8")
            except OSError:
                pass

    def _account_state(self, account_id: str) -> dict:
        acc = self._state.setdefault("accounts", {}).setdefault(account_id, _default_account_state())
        for k, v in _default_account_state().items():
            acc.setdefault(k, v)
        return acc

    # -- breaker per account ---------------------------------------------------- #

    def breaker_path(self, account_id: str) -> Path:
        return self.breaker_dir / f"{account_id}.json"

    def _breaker(self, account_id: str) -> CircuitBreaker:
        # Fresh instance each call: the FlowClient writes its own instance, so
        # reading from disk is the single source of truth across threads/processes.
        return CircuitBreaker(self.breaker_path(account_id))

    def cooldown_remaining_s(self, account_id: str) -> float:
        try:
            return float(self._breaker(account_id).snapshot().get("cooldown_remaining_s") or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0

    def breaker_snapshot(self, account_id: str) -> dict:
        try:
            return self._breaker(account_id).snapshot()
        except Exception:  # noqa: BLE001
            return {}

    # -- clients ------------------------------------------------------------------ #

    def client_for(self, account_id: str) -> FlowClient:
        with self._lock:
            client = self._clients.get(account_id)
            if client is None:
                client = FlowClient(
                    cdp_url=self.supervisor.cdp_url(self._port_of(account_id)),
                    out_dir=self.out_root,
                    breaker_path=self.breaker_path(account_id),
                    log=lambda m: self._log(f"[{account_id}] {m}"),
                )
                self._clients[account_id] = client
            return client

    def _account(self, account_id: str) -> Optional[AccountConfig]:
        for a in self.accounts:
            if a.id == account_id:
                return a
        return None

    def _port_of(self, account_id: str) -> int:
        a = self._account(account_id)
        return a.cdp_port if a else self.port_base

    def status_client(self) -> FlowClient:
        """Client used by /api/status: most-recently-used available account."""
        cands = self.available_accounts()
        if not cands:
            cands = [a for a in self.accounts if a.enabled] or self.accounts
        if not cands:
            return FlowClient(cdp_url=self.supervisor.cdp_url(self.port_base), out_dir=self.out_root,
                              breaker_path=self.breaker_path("default"))
        cands.sort(key=lambda a: -(int(self._account_state(a.id).get("last_used_at_ms") or 0)))
        return self.client_for(cands[0].id)

    # ------------------------------------------------------------------ #
    # Allocation (plan §1.1)
    # ------------------------------------------------------------------ #

    def is_available(self, account: AccountConfig) -> bool:
        return bool(account.enabled) and self.cooldown_remaining_s(account.id) <= 0

    def available_accounts(self) -> list[AccountConfig]:
        return [a for a in self.accounts if self.is_available(a)]

    def compute_allocation(self, j: int, q_target: Optional[int] = None,
                           max_ram: Optional[int] = None, n_avail: Optional[int] = None) -> int:
        """N_alloc(J) = min(N, M_RAM, max(1, ceil(J / Q_target))). 0 = không có account."""
        j = max(1, int(j))
        q = max(1, int(q_target or self.target_jobs_per_account))
        m = max(1, int(max_ram or self.max_active_browsers))
        n = len(self.available_accounts()) if n_avail is None else max(0, int(n_avail))
        if n <= 0:
            return 0
        need = max(1, math.ceil(j / q))
        return max(1, min(n, m, need))

    def select_working_set(self, n_alloc: int, *, affinity_shas: Optional[Iterable[str]] = None,
                           exclude: Iterable[str] = ()) -> list[AccountConfig]:
        """Wear-leveled selection with sticky reference affinity (plan §1.3/§2)."""
        shas = list(affinity_shas or [])
        excluded = set(exclude)
        cands = [a for a in self.available_accounts() if a.id not in excluded]

        def key(a: AccountConfig):
            st = self._account_state(a.id)
            hits = self.registry.count_for(a.id, shas) if shas else 0
            return (
                -hits,                                             # ưu tiên affinity
                int(st.get("total_completed") or 0),               # wear-leveling
                int(st.get("last_used_at_ms") or 0),
                a.id,
            )

        cands.sort(key=key)
        return cands[: max(0, int(n_alloc))]

    def affinity_shas_for_items(self, items: Iterable[dict]) -> set[str]:
        """sha256 của các reference file có sẵn trong batch (để chọn account ưu tiên)."""
        out: set[str] = set()
        for it in items:
            ref = it.get("reference_image_path") if isinstance(it, dict) else None
            if not ref:
                continue
            try:
                p = Path(ref)
                if not p.is_absolute():
                    p = ROOT / p
                if p.is_file():
                    out.add(sha256_file(p))
            except OSError:
                continue
        return out

    # ------------------------------------------------------------------ #
    # Working set lifecycle
    # ------------------------------------------------------------------ #

    def ensure_working_set(self, accounts: list[AccountConfig],
                           wait_timeout_s: float = 60.0) -> tuple[list[ActiveAccount], list[dict]]:
        """Wake the allocated browsers (on demand) — parallel, graceful degradation.

        Returns (active, errors). Raises only when NO account could be woken.
        """
        if not accounts:
            raise PoolUnavailableError("Không có account nào để wake.")

        active: list[ActiveAccount] = []
        errors: list[dict] = []
        results: list[tuple[AccountConfig, bool, Optional[Exception]]] = []
        with ThreadPoolExecutor(max_workers=min(8, len(accounts))) as ex:
            futs = {ex.submit(self._wake_one, a, wait_timeout_s): a for a in accounts}
            for fut, a in futs.items():
                try:
                    results.append((a, bool(fut.result()), None))
                except Exception as exc:  # noqa: BLE001
                    results.append((a, False, exc))
        for a, ok, exc in results:
            if ok:
                active.append(ActiveAccount(config=a, cdp_url=self.supervisor.cdp_url(a.cdp_port)))
            else:
                msg = f"{type(exc).__name__}: {exc}" if exc else "không rõ nguyên nhân"
                errors.append({"account_id": a.id, "error": msg})
                st = self._account_state(a.id)
                st["last_error"] = msg
                st["last_error_ms"] = int(time.time() * 1000)
                self._log(f"[pool] wake {a.id} lỗi: {msg}")
        if errors:
            self._save_state()
        if not active:
            raise PoolUnavailableError(
                "Không wake được browser nào: " + "; ".join(f"{e['account_id']}: {e['error'][:160]}" for e in errors)
            )
        return active, errors

    def _wake_one(self, account: AccountConfig, wait_timeout_s: float) -> bool:
        ok = self.supervisor.ensure_running(account.profile_id, account.cdp_port, wait_timeout_s=wait_timeout_s)
        if ok:
            st = self._account_state(account.id)
            st["last_woken_at_ms"] = int(time.time() * 1000)
            self._save_state()
        return ok

    def acquire_single(self) -> ActiveAccount:
        """One account for a single job (wear-leveling, wake on demand)."""
        selected = self.select_working_set(1)
        if not selected:
            raise PoolUnavailableError(
                "Không có account khả dụng (tất cả đang cooldown/disabled). "
                "Kiểm tra /api/pool hoặc chờ hết cooldown."
            )
        active, _errors = self.ensure_working_set(selected)
        return active[0]

    def promote_standby(self, exclude: Iterable[str] = ()) -> Optional[ActiveAccount]:
        """Hot-spare: rút 1 account dự phòng (plan §1.3 điểm 3). None nếu hết."""
        selected = self.select_working_set(1, exclude=exclude)
        if not selected:
            return None
        try:
            active, _errors = self.ensure_working_set(selected)
        except PoolUnavailableError as exc:
            self._log(f"[pool] promote thất bại: {exc}")
            return None
        return active[0] if active else None

    # -- batch bookkeeping ---------------------------------------------------- #

    def set_current_batch(self, job_id: str, j: int, n_alloc: int, account_ids: list[str]) -> None:
        with self._lock:
            self._current_batch = {
                "job_id": job_id, "j": int(j), "n_alloc": int(n_alloc),
                "accounts": list(account_ids), "ts_ms": int(time.time() * 1000),
            }

    def end_batch(self) -> None:
        with self._lock:
            if self._current_batch is not None:
                self._state["last_batch"] = self._current_batch
                self._current_batch = None
                self._save_state()

    def current_batch(self) -> Optional[dict]:
        return self._current_batch

    # -- results --------------------------------------------------------------- #

    def report_item_result(self, account_id: str, status: str, error: Optional[str] = None) -> None:
        with self._lock:
            st = self._account_state(account_id)
            now = int(time.time() * 1000)
            st["last_used_at_ms"] = now
            if status in ("ok", "ok_no_download"):
                st["total_completed"] = int(st.get("total_completed") or 0) + 1
            elif status == "rejected":
                st["total_rejected"] = int(st.get("total_rejected") or 0) + 1
            elif status == "failed":
                st["total_failed"] = int(st.get("total_failed") or 0) + 1
                st["last_error"] = (error or "unknown")[:400]
                st["last_error_ms"] = now
            self._save_state()

    # -- account actions (API) ---------------------------------------------------- #

    def wake_account(self, account_id: str) -> dict:
        a = self._account(account_id)
        if a is None:
            raise KeyError(f"account không tồn tại: {account_id}")
        active, errors = self.ensure_working_set([a])
        return {"ok": bool(active), "errors": errors}

    def hibernate_account(self, account_id: str) -> dict:
        a = self._account(account_id)
        if a is None:
            raise KeyError(f"account không tồn tại: {account_id}")
        return self.supervisor.hibernate(a.profile_id, a.cdp_port)

    def reset_account(self, account_id: str) -> dict:
        a = self._account(account_id)
        if a is None:
            raise KeyError(f"account không tồn tại: {account_id}")
        self._breaker(account_id).clear_cooldown()
        with self._lock:
            st = self._account_state(account_id)
            st["last_error"] = None
            st["last_error_ms"] = 0
            self._save_state()
        return {"ok": True}

    # ------------------------------------------------------------------ #
    # Snapshot for UI/API
    # ------------------------------------------------------------------ #

    def _probe_ports(self, accounts: list[AccountConfig]) -> dict[str, bool]:
        if not accounts:
            return {}
        out: dict[str, bool] = {}
        with ThreadPoolExecutor(max_workers=min(8, len(accounts))) as ex:
            futs = {ex.submit(self.supervisor.is_alive, a.cdp_port, 1.0): a for a in accounts}
            for fut, a in futs.items():
                try:
                    out[a.id] = bool(fut.result())
                except Exception:  # noqa: BLE001
                    out[a.id] = False
        return out

    def snapshot(self, probe: bool = True) -> dict:
        cb = self._current_batch
        active_ids = set((cb or {}).get("accounts") or [])
        with self._lock:
            running = self._probe_ports(self.accounts) if probe else {}
            out_accounts = []
            for a in self.accounts:
                st = self._account_state(a.id)
                cd = self.cooldown_remaining_s(a.id)
                bid = self.breaker_snapshot(a.id)
                status = "disabled" if not a.enabled else ("cooldown" if cd > 0 else "ready")
                out_accounts.append({
                    "id": a.id,
                    "profile_id": a.profile_id,
                    "cdp_port": a.cdp_port,
                    "cdp_url": self.supervisor.cdp_url(a.cdp_port),
                    "enabled": bool(a.enabled),
                    "note": a.note or None,
                    "running": bool(running.get(a.id, False)),
                    "managed": self.supervisor.is_managed(a.profile_id),
                    "status": status,
                    "role": "active" if a.id in active_ids else "standby",
                    "cooldown_remaining_s": round(cd, 1),
                    "cooldown_reason": (bid.get("cooldown_reason") or None) if cd > 0 else None,
                    "total_completed": int(st.get("total_completed") or 0),
                    "total_rejected": int(st.get("total_rejected") or 0),
                    "total_failed": int(st.get("total_failed") or 0),
                    "last_used_at_ms": st.get("last_used_at_ms") or None,
                    "last_error": st.get("last_error"),
                })
            n_avail = sum(1 for x in out_accounts if x["enabled"] and x["status"] != "cooldown")
            return {
                "n_total": len(self.accounts),
                "n_available": n_avail,
                "target_jobs_per_account": self.target_jobs_per_account,
                "max_active_browsers": self.max_active_browsers,
                "working_set": sorted(active_ids),
                "current_batch": cb,
                "last_batch": self._state.get("last_batch"),
                "accounts": out_accounts,
                "reference_cache": self.registry.stats(),
            }
