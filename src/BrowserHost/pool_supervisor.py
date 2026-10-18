"""PoolSupervisor — wake / hibernate CloakBrowser profiles on demand (Task 1).

Part of the N-account pool (docs/upgrade_plan_n_account_pool.md §4):

    * The pool decides WHICH accounts are in the working set (N_alloc).
    * This module only knows how to bring a profile's browser UP
      (``launch_profile.py``, detached) and how to put it to SLEEP again
      (PID-tracked ``taskkill``), then confirm the state via CDP.

Policy notes (AGENTS.md §1, plan §1.3):

    * Never launch all profiles at startup — only the allocated set is woken.
    * ``ensure_running`` first probes ``/json/version``: if a browser already
      answers on the account's port (e.g. the user launched it manually) it is
      simply attached to, never duplicated.
    * ``hibernate`` only closes browsers that the pool itself launched (PID
      file written by ``launch_profile.py --pid-file``). A browser the user
      started by hand is left untouched — the supervisor reports
      ``not_managed`` instead.

Usage:
    sup = PoolSupervisor()
    sup.ensure_running("acc_01", 9222)     # attach or launch + wait for CDP
    sup.is_alive(9222)                     # cheap HTTP probe
    sup.hibernate("acc_01", 9222)          # graceful -> forced close (managed only)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAUNCH_SCRIPT = Path(__file__).resolve().parent / "launch_profile.py"
DEFAULT_VAULT = PROJECT_ROOT / "browser_vault"
DEFAULT_PID_DIR = PROJECT_ROOT / "out" / "pids"


class SupervisorError(RuntimeError):
    """Browser could not be woken / hibernated."""


class PoolSupervisor:
    """Stateless-ish helper: chooses launch vs attach, tracks PIDs on disk."""

    def __init__(
        self,
        vault_dir: Optional[Path] = None,
        pid_dir: Optional[Path] = None,
        python: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.vault_dir = Path(vault_dir) if vault_dir else DEFAULT_VAULT
        self.pid_dir = Path(pid_dir) if pid_dir else DEFAULT_PID_DIR
        self.python = python or sys.executable
        self._log = log or (lambda *_: None)

    # -- CDP probing ---------------------------------------------------------- #

    @staticmethod
    def cdp_url(port: int) -> str:
        return f"http://127.0.0.1:{int(port)}"

    def is_alive(self, port: int, timeout_s: float = 1.5) -> bool:
        """True when a CDP endpoint answers on the port (any browser)."""
        try:
            r = requests.get(self.cdp_url(port) + "/json/version", timeout=timeout_s)
            return r.status_code == 200
        except Exception:  # noqa: BLE001 - offline is a normal state here
            return False

    # -- PID tracking (only for pool-launched browsers) ------------------------ #

    def pid_path(self, profile_id: str) -> Path:
        return self.pid_dir / f"{profile_id}.pid"

    def read_pid(self, profile_id: str) -> Optional[int]:
        try:
            raw = self.pid_path(profile_id).read_text(encoding="utf-8").strip()
            return int(raw) if raw else None
        except Exception:  # noqa: BLE001
            return None

    def is_managed(self, profile_id: str) -> bool:
        """True when the pool launched this profile and the process still runs."""
        pid = self.read_pid(profile_id)
        return bool(pid and self.is_process_running(pid))

    @staticmethod
    def is_process_running(pid: int) -> bool:
        if not pid or pid <= 0:
            return False
        if sys.platform == "win32":
            try:
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=10,
                ).stdout or ""
                return f'"{pid}"' in out
            except Exception:  # noqa: BLE001
                return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    # -- wake ------------------------------------------------------------------ #

    def ensure_running(self, profile_id: str, port: int, wait_timeout_s: float = 60.0) -> bool:
        """Attach if CDP is alive; otherwise launch the profile and wait for CDP.

        Returns True when the browser answers on ``port``. Raises
        :class:`SupervisorError` with the launcher tail on failure.
        """
        if self.is_alive(port):
            self._log(f"[{profile_id}] CDP :{port} đã sống — attach (không launch thêm)")
            return True

        cmd = [
            self.python, str(LAUNCH_SCRIPT),
            "--profile", profile_id,
            "--port", str(int(port)),
            "--wait", "--wait-timeout", str(float(wait_timeout_s)),
            "--pid-file", str(self.pid_path(profile_id)),
            "--vault-dir", str(self.vault_dir),
        ]
        self._log(f"[{profile_id}] wake browser :{port} (launch_profile subprocess)")
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=wait_timeout_s + 90.0, cwd=str(PROJECT_ROOT),
            )
        except subprocess.TimeoutExpired as exc:
            raise SupervisorError(f"[{profile_id}] launch_profile timed out sau {wait_timeout_s + 90:.0f}s") from exc

        if proc.returncode == 0 and self.is_alive(port):
            return True

        tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-6:]
        hint = (
            "Gợi ý: kiểm tra port trùng, profile hỏng, hoặc CloakBrowser chưa cài "
            "(python -m cloakbrowser info)."
        )
        raise SupervisorError(
            f"[{profile_id}] không wake được browser trên :{port} "
            f"(rc={proc.returncode}). {hint} Log cuối: " + " | ".join(tail)
        )

    # -- hibernate --------------------------------------------------------------- #

    def hibernate(self, profile_id: str, port: int, graceful_timeout_s: float = 6.0) -> dict:
        """Close a pool-managed browser. Never touches user-launched browsers.

        Returns {"ok": bool, "reason": str}; ``reason == "not_managed"`` means
        the browser was not started by the pool (leave it alone).
        """
        pid = self.read_pid(profile_id)
        if not pid:
            return {"ok": False, "reason": "not_managed"}
        if not self.is_process_running(pid):
            self._pid_path_unlink(profile_id)
            return {"ok": True, "reason": "already_down"}

        self._log(f"[{profile_id}] hibernate pid={pid} (graceful taskkill /T)")
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T"], capture_output=True, text=True, timeout=15)
        except Exception as exc:  # noqa: BLE001
            self._log(f"[{profile_id}] graceful taskkill lỗi: {exc}")

        deadline = time.time() + max(1.0, graceful_timeout_s)
        while time.time() < deadline:
            if not self.is_process_running(pid):
                break
            time.sleep(0.4)

        if self.is_process_running(pid):
            self._log(f"[{profile_id}] còn sống — force taskkill /F")
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=15)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "reason": f"taskkill_failed: {exc}"}
            time.sleep(0.8)

        still = self.is_process_running(pid)
        if not still:
            self._pid_path_unlink(profile_id)
        return {"ok": not still, "reason": "closed" if not still else "still_running"}

    def _pid_path_unlink(self, profile_id: str) -> None:
        try:
            self.pid_path(profile_id).unlink(missing_ok=True)
        except OSError:
            pass
