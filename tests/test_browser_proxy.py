"""Task 2 — per-browser proxy config: normalization, argv wiring, persistence.

No browser is launched: ``launch_profile.build_command`` only needs the
cloakbrowser SDK to render argv, and the pool tests use ``DummySupervisor``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.BrowserHost.launch_profile import (
    build_command,
    describe_proxy,
    normalize_proxy,
    profile_browser_pid,
    proxy_to_url,
)
from src.Workflows.account_pool import AccountPoolManager, proxy_label

ROOT = Path(__file__).resolve().parents[1]

BASE_CFG = {
    "profile_id": "acc_01",
    "fingerprint_seed": 65547266,
    "platform": "windows",
    "timezone_id": "Asia/Ho_Chi_Minh",
    "locale": "en-US",
    "extra_flags": ["--webrtc-ip-handling-policy=disable_non_proxied_udp"],
}


# -- normalization ---------------------------------------------------------- #


@pytest.mark.parametrize("value", [None, "", "   ", {"server": ""}, {}])
def test_empty_proxy_means_direct(value):
    assert normalize_proxy(value) is None
    assert proxy_to_url(value) == ""


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.2.3.4:8080", "http://1.2.3.4:8080"),
        ("host.example:3128", "http://host.example:3128"),
        ("http://host:8080", "http://host:8080"),
        ("https://host:8443", "https://host:8443"),
        ("socks5://host:1080", "socks5://host:1080"),
        ("user:pass@host:8080", "http://user:pass@host:8080"),
        ("http://user:pass@host:8080", "http://user:pass@host:8080"),
        ("socks5://user:pass@host:1080", "socks5://user:pass@host:1080"),
        ({"server": "host:8080", "username": "u", "password": "p"}, "http://u:p@host:8080"),
        ({"server": "http://host:8080"}, "http://host:8080"),
        ({"server": "http://host:8080", "username": "u"}, "http://u@host:8080"),
    ],
)
def test_proxy_to_url(value, expected):
    assert proxy_to_url(value) == expected


def test_proxy_scheme_and_port_are_validated():
    with pytest.raises(ValueError, match="scheme"):
        normalize_proxy("ftp://host:21")
    with pytest.raises(ValueError, match="port"):
        normalize_proxy("host-without-port")
    with pytest.raises(ValueError, match="proxy"):
        normalize_proxy(12345)


def test_describe_proxy_never_leaks_password():
    label = describe_proxy("http://user:s3cr3t@host:8080")
    assert "s3cr3t" not in label
    assert "user@host:8080" in label
    assert describe_proxy(None).startswith("direct")


# -- argv wiring ------------------------------------------------------------ #


def _argv(cfg: dict, tmp_path: Path) -> list[str]:
    return build_command(cfg, "chromium", tmp_path / "user_data", 4022)


def test_direct_ip_adds_no_proxy_flag(tmp_path):
    for proxy in (None, "", "   "):
        argv = _argv({**BASE_CFG, "proxy": proxy}, tmp_path)
        assert not [a for a in argv if a.startswith("--proxy-server")]


def test_proxy_flag_is_injected(tmp_path):
    argv = _argv({**BASE_CFG, "proxy": "socks5://u:p@1.2.3.4:1080"}, tmp_path)
    assert "--proxy-server=socks5://u:p@1.2.3.4:1080" in argv


def test_proxy_bypass_list(tmp_path):
    argv = _argv({**BASE_CFG, "proxy": "http://h:8080", "proxy_bypass": ["<-loopback>", "*.local"]}, tmp_path)
    assert "--proxy-bypass-list=<-loopback>,*.local" in argv


def test_fingerprint_seed_is_stable_across_builds(tmp_path):
    first = _argv({**BASE_CFG, "proxy": None}, tmp_path)
    second = _argv({**BASE_CFG, "proxy": "http://h:8080"}, tmp_path)
    fp = lambda argv: [a for a in argv if a.startswith("--fingerprint=")]
    assert fp(first) == fp(second) == ["--fingerprint=65547266"]


# -- pool model / persistence ----------------------------------------------- #


class DummySupervisor:
    def __init__(self):
        self.alive: set[int] = set()

    def cdp_url(self, port: int) -> str:
        return f"http://127.0.0.1:{port}"

    def is_alive(self, port: int, timeout_s: float = 1.5) -> bool:
        return port in self.alive

    def ensure_running(self, profile_id: str, port: int, wait_timeout_s: float = 60.0) -> bool:
        self.alive.add(port)
        return True

    def hibernate(self, profile_id: str, port: int, graceful_timeout_s: float = 6.0) -> dict:
        return {"ok": True, "reason": "closed"}

    def is_managed(self, profile_id: str) -> bool:
        return False


def _pool(tmp_path: Path) -> AccountPoolManager:
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = tmp_path / "accounts_pool.json"
    cfg.write_text(json.dumps({
        "port_base": 4022,
        "accounts": [{"id": "acc_01", "profile_id": "acc_01", "cdp_port": 4022}],
    }), encoding="utf-8")
    return AccountPoolManager(
        config_path=cfg,
        state_path=tmp_path / "state.json",
        breaker_dir=tmp_path / "breakers",
        ref_cache_path=tmp_path / "refs.json",
        vault_dir=vault,
        out_root=tmp_path / "out",
        supervisor=DummySupervisor(),
    )


def test_account_proxy_persists_and_mirrors_into_vault(tmp_path):
    pool = _pool(tmp_path)
    acc = pool.update_account("acc_01", proxy="socks5://u:p@1.2.3.4:1080")

    saved = json.loads(Path(pool.config_path).read_text(encoding="utf-8"))
    assert saved["accounts"][0]["proxy"] == "socks5://u:p@1.2.3.4:1080"
    assert acc.proxy == "socks5://u:p@1.2.3.4:1080"

    profile_cfg = json.loads((pool.vault_dir / "acc_01" / "config.json").read_text(encoding="utf-8"))
    assert profile_cfg["proxy"] == "socks5://u:p@1.2.3.4:1080"


def test_clearing_proxy_falls_back_to_direct(tmp_path):
    pool = _pool(tmp_path)
    pool.update_account("acc_01", proxy="http://u:p@h:8080")
    pool.update_account("acc_01", clear_proxy=True)

    assert pool._account("acc_01").proxy is None
    profile_cfg = json.loads((pool.vault_dir / "acc_01" / "config.json").read_text(encoding="utf-8"))
    assert profile_cfg["proxy"] is None


def test_invalid_proxy_is_rejected(tmp_path):
    pool = _pool(tmp_path)
    with pytest.raises(ValueError):
        pool.update_account("acc_01", proxy="ftp://h:21")
    with pytest.raises(ValueError):
        pool.add_account("acc_02", proxy="h-without-port", create_profile=False)


def test_snapshot_exposes_credential_free_label(tmp_path):
    pool = _pool(tmp_path)
    pool.update_account("acc_01", proxy="http://user:s3cr3t@host:8080")
    snap = pool.snapshot(probe=False)
    row = snap["accounts"][0]
    assert row["has_proxy"] is True
    assert "s3cr3t" not in (row["proxy"] or "")
    assert proxy_label(pool._account("acc_01").proxy).endswith("host:8080")


# --------------------------------------------------------------------------- #
# Guard chống mở tab trùng khi profile đã có browser sống
# --------------------------------------------------------------------------- #

def test_no_live_browser_for_an_unused_profile(tmp_path):
    """Profile chưa chạy ⇒ không có PID, launch được bình thường."""
    assert profile_browser_pid(tmp_path / "user_data") is None


def test_live_browser_is_detected_by_user_data_dir(tmp_path):
    """Tìm đúng tiến trình theo `--user-data-dir`, không đoán theo tên tiến trình.

    Chromium không cho hai tiến trình dùng chung một `--user-data-dir`: lần launch thứ hai
    sẽ chuyển URL sang cửa sổ cũ và **mở thêm một tab** rồi thoát. Đó là cách một cửa sổ
    `flow.google.com` tích ra 8 tab trong cùng một phiên làm việc (đo 2026‑11‑12), mỗi lần
    `run.ps1 start` khi browser còn sống là một tab.
    """
    from unittest.mock import MagicMock, patch

    target = (tmp_path / "user_data").resolve()

    def fake_iter(fields):
        # 1) renderer của CÙNG profile — không phải tiến trình browser
        r = MagicMock()
        r.info = {"pid": 11, "name": "chrome.exe",
                  "cmdline": ["chrome.exe", "--type=renderer", f"--user-data-dir={target}"]}
        # 2) browser của profile KHÁC
        o = MagicMock()
        o.info = {"pid": 22, "name": "chrome.exe",
                  "cmdline": ["chrome.exe", "--user-data-dir=D:/other/user_data"]}
        # 3) browser của CHÍNH profile này
        hit = MagicMock()
        hit.info = {"pid": 33, "name": "chrome.exe",
                    "cmdline": ["chrome.exe", f"--user-data-dir={target}", "--remote-debugging-port=4023"]}
        return iter([r, o, hit])

    fake_psutil = MagicMock()
    fake_psutil.process_iter.side_effect = fake_iter
    fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        import importlib
        import src.BrowserHost.launch_profile as lp
        importlib.reload(lp)
        try:
            assert lp.profile_browser_pid(target) == 33
        finally:
            importlib.reload(lp)
