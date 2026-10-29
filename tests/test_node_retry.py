"""Task 3 — node-level auto-retry for PUBLIC_ERROR_UNUSUAL_ACTIVITY.

Timers are injected through ``delays``(tiny values) so the suite stays fast;
the real schedule is asserted separately from the module constants.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from src.Workflows.node_retry import (
    RETRY_DELAYS_S,
    NodeExecutionError,
    RetryAborted,
    is_unusual_activity,
    run_with_retry,
)

ANTI_ABUSE = "PERMISSION_DENIED: Bị hệ thống chống lạm dụng từ chối (PUBLIC_ERROR_UNUSUAL_ACTIVITY)"


def _rejected(reason: str = "PERMISSION_DENIED", hint: str = "") -> SimpleNamespace:
    return SimpleNamespace(status="rejected", reason=reason, detail=ANTI_ABUSE, hint=hint, anti_abuse=True)


def _ok() -> SimpleNamespace:
    return SimpleNamespace(status="ok", reason=None, hint=None, anti_abuse=False)


# -- schedule --------------------------------------------------------------- #


def test_real_schedule_matches_requirement():
    assert RETRY_DELAYS_S["image"] == (10.0, 20.0)
    assert RETRY_DELAYS_S["video"] == (30.0, 60.0)


# -- detection -------------------------------------------------------------- #


def test_detects_anti_abuse_results_and_exceptions():
    assert is_unusual_activity(_rejected())
    assert is_unusual_activity({"status": "rejected", "reason": "PUBLIC_ERROR_UNUSUAL_ACTIVITY"})
    assert is_unusual_activity(RuntimeError(ANTI_ABUSE))
    assert is_unusual_activity({"status": "rejected", "grpc_code": 7})


def test_ignores_other_rejections_and_successes():
    assert not is_unusual_activity(SimpleNamespace(status="rejected", reason="PROMINENT_PEOPLE_FILTER"))
    assert not is_unusual_activity(SimpleNamespace(status="ok", detail=ANTI_ABUSE))
    assert not is_unusual_activity(RuntimeError("file not found"))


# -- retry behaviour -------------------------------------------------------- #


def _collect(logs: list):
    def log(level, message, data=None):
        logs.append((level, message, data or {}))
    return log


def test_retries_twice_then_succeeds():
    calls = {"n": 0}
    logs: list = []

    def fn():
        calls["n"] += 1
        return _ok() if calls["n"] == 3 else _rejected()

    res = run_with_retry(fn, kind="image", log=_collect(logs), delays=(0.01, 0.01))
    assert res.status == "ok"
    assert calls["n"] == 3
    retries = [m for lvl, m, _ in logs if lvl == "retry"]
    assert len(retries) == 2
    assert retries[0].startswith("[Retry 1/2]")
    assert "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in retries[0]
    assert "tạo ảnh" in retries[0]
    assert retries[1].startswith("[Retry 2/2]")


def test_video_retry_log_names_the_task():
    logs: list = []
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            return _rejected()
        return _ok()

    run_with_retry(fn, kind="video", log=_collect(logs), delays=(0.01, 0.01))
    retry = [m for lvl, m, _ in logs if lvl == "retry"][0]
    assert "khi tạo video" in retry


def test_exhausted_budget_raises_execution_error():
    calls = {"n": 0}
    logs: list = []

    def fn():
        calls["n"] += 1
        return _rejected(hint="nên chờ vài phút rồi thử lại")

    with pytest.raises(NodeExecutionError) as ei:
        run_with_retry(fn, kind="video", log=_collect(logs), delays=(0.01, 0.01))
    err = ei.value
    assert err.code == "EXECUTION_ERROR"
    assert calls["n"] == 3          # 1 initial + 2 retries
    assert err.attempts == 3
    assert "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in str(err)


def test_non_anti_abuse_errors_are_not_retried():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("Không tìm thấy ảnh đính kèm")

    with pytest.raises(ValueError):
        run_with_retry(fn, kind="video", delays=(0.01, 0.01))
    assert calls["n"] == 1


def test_exception_with_marker_is_retried_then_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(ANTI_ABUSE)
        return _ok()

    assert run_with_retry(fn, kind="image", delays=(0.01, 0.01)).status == "ok"
    assert calls["n"] == 2


def test_abort_interrupts_the_wait():
    abort = threading.Event()
    logs: list = []
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return _rejected()

    def stop_soon():
        time.sleep(0.15)
        abort.set()

    threading.Thread(target=stop_soon, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(RetryAborted):
        run_with_retry(fn, kind="video", log=_collect(logs), abort=abort, delays=(30.0, 60.0))
    assert time.monotonic() - started < 3.0        # never waits the full 30 s
    assert calls["n"] == 1
    assert any("Đã hủy chờ" in m for _, m, _ in logs)


def test_logger_with_two_args_is_tolerated():
    seen: list = []

    def log(level, message):        # no data kwarg
        seen.append((level, message))

    run_with_retry(lambda: _ok(), kind="image", log=log, delays=(0.01, 0.01))
    assert seen == []               # success on the first try logs nothing
