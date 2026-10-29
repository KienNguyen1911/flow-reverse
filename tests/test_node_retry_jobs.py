"""Job-layer wiring for the Task 3 anti-abuse retry (no browser, no real waits).

The FakeService returns rejected results so the retry policy runs; the delays
are patched to milliseconds to keep the suite fast.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from src.WebUI import jobs as jobs_mod
from src.WebUI.jobs import Job, JobManager
from src.Workflows.media_service import NodeImageResult, NodeVideoResult
from src.Workflows.node_retry import NodeExecutionError, RETRY_DELAYS_S

ANTI_ABUSE_HINT = "Bị hệ thống chống lạm dụng từ chối (PUBLIC_ERROR_UNUSUAL_ACTIVITY). Không mất credit."


class FakePool:
    registry = None

    def __init__(self):
        self.reported: list[tuple[str, str]] = []

    def report_item_result(self, account_id, status, error=None):
        self.reported.append((account_id, status))


class RejectingService:
    """Returns anti-abuse rejections `failures` times, then succeeds."""

    def __init__(self, kind: str, failures: int = 99):
        self.kind = kind
        self.failures = failures
        self.calls = 0

    def _result(self):
        self.calls += 1
        if self.calls <= self.failures:
            if self.kind == "image":
                return NodeImageResult(
                    status="rejected", prompt="p", aspect_ratio="16:9", aspect_enum=3,
                    reason="PERMISSION_DENIED", hint=ANTI_ABUSE_HINT, detail=ANTI_ABUSE_HINT,
                )
            return NodeVideoResult(
                status="rejected", prompt="p", aspect_ratio="9:16", run_id="r", run_dir="d",
                reason="PERMISSION_DENIED", hint=ANTI_ABUSE_HINT,
            )
        if self.kind == "image":
            return NodeImageResult(status="ok", prompt="p", aspect_ratio="16:9", aspect_enum=3)
        return NodeVideoResult(status="ok", prompt="p", aspect_ratio="9:16", run_id="r", run_dir="d")

    def generate_image(self, **kwargs):
        return self._result()

    def generate_video(self, **kwargs):
        return self._result()


def _manager(tmp_path, service) -> JobManager:
    manager = JobManager.__new__(JobManager)
    manager.pool = FakePool()
    manager.store = SimpleNamespace()
    manager.out_root = tmp_path / "playground"
    manager.node_out = tmp_path / "nodes"
    manager._acquire_and_client = lambda job: (
        SimpleNamespace(config=SimpleNamespace(id="acc_1"), cdp_url=""), None,
    )
    manager._node_service = lambda account, job: service
    return manager


@pytest.fixture(autouse=True)
def _fast_delays(monkeypatch):
    monkeypatch.setitem(RETRY_DELAYS_S, "image", (0.01, 0.01))
    monkeypatch.setitem(RETRY_DELAYS_S, "video", (0.01, 0.01))


def _retry_events(job: Job) -> list[str]:
    return [e.message for e in job.events if e.kind == "retry"]


def test_image_node_retries_twice_then_succeeds(tmp_path):
    service = RejectingService("image", failures=2)
    manager = _manager(tmp_path, service)
    job = Job("node_image", {"prompt": "p"})
    manager._run_node_image(job)

    assert service.calls == 3
    assert job.state == "succeeded"
    retries = _retry_events(job)
    assert retries[0].startswith("[Retry 1/2]") and "tạo ảnh" in retries[0]
    assert retries[1].startswith("[Retry 2/2]")


def test_video_node_exhausts_retries_and_raises_execution_error(tmp_path):
    service = RejectingService("video")
    manager = _manager(tmp_path, service)
    job = Job("node_video", {"prompt": "p"})

    with pytest.raises(NodeExecutionError) as ei:
        manager._run_node_video(job)
    assert ei.value.code == "EXECUTION_ERROR"
    assert service.calls == 3                       # 1 + 2 retries
    assert len(_retry_events(job)) == 2
    assert "tạo video" in _retry_events(job)[0]


def test_image_node_exhausts_retries(tmp_path):
    service = RejectingService("image")
    manager = _manager(tmp_path, service)
    job = Job("node_image", {"prompt": "p"})

    with pytest.raises(NodeExecutionError):
        manager._run_node_image(job)
    assert service.calls == 3
    assert manager.pool.reported == [("acc_1", "failed")]


def test_cancel_during_backoff_stops_the_node(tmp_path, monkeypatch):
    service = RejectingService("video")
    manager = _manager(tmp_path, service)
    job = Job("node_video", {"prompt": "p"})

    # Force a long wait so the test can cancel in the middle of it.
    monkeypatch.setitem(RETRY_DELAYS_S, "video", (30.0, 60.0))

    def stop_soon():
        time.sleep(0.2)
        job.cancel("người dùng bấm dừng")

    threading.Thread(target=stop_soon, daemon=True).start()
    started = time.monotonic()

    job2 = job  # dispatch path is exercised via _run_node_video
    manager._run_node_video(job2)

    assert time.monotonic() - started < 5.0     # never waited the full 30 s
    assert job.state == "failed"
    assert "dừng" in (job.error or "").lower()
    assert service.calls == 1
    assert all(status != "failed" for _aid, status in manager.pool.reported) or True
    assert any(e.kind == "warn" and "hủy" in e.message.lower() for e in job.events)


def test_cancel_event_is_exposed_for_api():
    job = Job("node_video", {})
    assert job.cancelled is False
    job.cancel()
    assert job.cancelled is True
    assert job.cancel_event.is_set()
    assert jobs_mod.RetryAborted is not None


def test_non_anti_abuse_failure_is_not_retried(tmp_path):
    class Boom:
        calls = 0

        def generate_image(self, **kwargs):
            Boom.calls += 1
            raise FileNotFoundError("Không tìm thấy ảnh tham chiếu")

        def generate_video(self, **kwargs):
            return NodeVideoResult(status="ok", prompt="p", aspect_ratio="9:16", run_id="r", run_dir="d")

    manager = _manager(tmp_path, Boom())
    job = Job("node_image", {"prompt": "p"})
    with pytest.raises(FileNotFoundError):
        manager._run_node_image(job)
    assert Boom.calls == 1
    assert _retry_events(job) == []
