"""Job-layer wiring for canvas node jobs (result → API URL mapping, state)."""

from __future__ import annotations

from types import SimpleNamespace

from src.WebUI.jobs import Job, JobManager
from src.Workflows.media_service import NodeImageResult, NodeVideoResult


class FakePool:
    registry = None

    def __init__(self):
        self.reported: list[tuple[str, str]] = []

    def report_item_result(self, account_id, status, error=None):
        self.reported.append((account_id, status))


class FakeService:
    def __init__(self, image: NodeImageResult | None = None, video: NodeVideoResult | None = None):
        self._image = image
        self._video = video

    def generate_image(self, **kwargs):
        return self._image

    def generate_video(self, **kwargs):
        return self._video


def _manager(tmp_path, service: FakeService) -> JobManager:
    manager = JobManager.__new__(JobManager)  # no worker thread for unit tests
    manager.pool = FakePool()
    manager.store = SimpleNamespace()
    manager.out_root = tmp_path / "playground"
    manager.node_out = tmp_path / "nodes"
    manager._acquire_and_client = lambda job: (SimpleNamespace(config=SimpleNamespace(id="acc_1"), cdp_url=""), None)
    manager._node_service = lambda account, job: service
    return manager


def test_node_image_job_maps_file_url_and_state(tmp_path):
    run_dir = tmp_path / "nodes" / "20261028_120000_a_red_apple"
    run_dir.mkdir(parents=True)
    file_path = run_dir / "a_red_apple.jpg"
    file_path.write_bytes(b"jpeg")
    res = NodeImageResult(
        status="ok",
        prompt="a red apple",
        aspect_ratio="16:9",
        aspect_enum=3,
        run_id=run_dir.name,
        run_dir=str(run_dir),
        file_path=str(file_path),
        file_bytes=4,
    )
    manager = _manager(tmp_path, FakeService(image=res))
    job = Job("node_image", {"prompt": "a red apple"})
    manager._run_node_image(job)

    assert job.state == "succeeded"
    assert job.result["file_url"] == f"/api/node/files/{run_dir.name}/a_red_apple.jpg"
    assert job.result["account_id"] == "acc_1"
    assert manager.pool.reported == [("acc_1", "ok")]


def test_node_image_job_rejected_state(tmp_path):
    res = NodeImageResult(status="rejected", prompt="p", aspect_ratio="16:9", aspect_enum=3, reason="anti_abuse")
    manager = _manager(tmp_path, FakeService(image=res))
    job = Job("node_image", {"prompt": "p"})
    manager._run_node_image(job)

    assert job.state == "rejected"
    assert job.result["reason"] == "anti_abuse"


def test_node_video_job_maps_urls(tmp_path):
    run_dir = tmp_path / "nodes" / "video_20261028_120000"
    run_dir.mkdir(parents=True)
    video = run_dir / "video.mp4"
    video.write_bytes(b"ftyp")
    frame = run_dir / "starting_frame.png"
    frame.write_bytes(b"png")
    res = NodeVideoResult(
        status="ok",
        prompt="pan",
        aspect_ratio="9:16",
        run_id=run_dir.name,
        run_dir=str(run_dir),
        video_path=str(video),
        video_bytes=4,
        frame_path=str(frame),
        frame_source="provided",
    )
    manager = _manager(tmp_path, FakeService(video=res))
    job = Job("node_video", {"prompt": "pan"})
    manager._run_node_video(job)

    assert job.state == "succeeded"
    assert job.result["video_url"] == f"/api/node/files/{run_dir.name}/video.mp4"
    assert job.result["frame_url"] == f"/api/node/files/{run_dir.name}/starting_frame.png"
