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
    assert job.result["account_id"] == "acc_1"


def test_node_video_job_forwards_composer_config(tmp_path):
    """The job must pass model/sub_mode/count/workspace_project_id through, not silently drop them."""
    seen: dict = {}

    class RecordingService(FakeService):
        def generate_video(self, **kwargs):
            seen.update(kwargs)
            return NodeVideoResult(
                status="dry_run",
                prompt="pan",
                aspect_ratio="16:9",
                run_id="r1",
                run_dir=str(tmp_path / "r1"),
                sub_mode="ingredients",
                model="veo_3_1_fast",
                model_key="veo_3_1_t2v_fast",
                count=2,
            )

    manager = _manager(tmp_path, RecordingService())
    job = Job(
        "node_video",
        {
            "prompt": "pan",
            "model": "veo_3_1_fast",
            "sub_mode": "ingredients",
            "count": 2,
            "duration_s": 8,
            "resolution": "720p",
            "agent_mode": True,
            "dry_run": True,
            "workspace_project_id": "ws_prj_999",
        },
    )
    manager._run_node_video(job)

    assert job.state == "succeeded"
    assert seen["model"] == "veo_3_1_fast"
    assert seen["sub_mode"] == "ingredients"
    assert seen["count"] == 2
    assert seen["agent_mode"] is True
    assert seen["workspace_project_id"] == "ws_prj_999"
    assert job.result["account_id"] == "acc_1"
    assert job.result["model"] == "veo_3_1_fast"
    assert job.result["sub_mode"] == "ingredients"
    assert job.result["count"] == 2


def test_node_video_job_forwards_reference_image_paths(tmp_path):
    seen: dict = {}

    class RecordingService(FakeService):
        def generate_video(self, **kwargs):
            seen.update(kwargs)
            return NodeVideoResult(
                status="dry_run",
                prompt="walk",
                aspect_ratio="9:16",
                run_id="r2",
                run_dir=str(tmp_path / "r2"),
                sub_mode="ingredients",
                reference_image_paths=kwargs.get("reference_image_paths"),
            )

    manager = _manager(tmp_path, RecordingService())
    job = Job(
        "node_video",
        {
            "prompt": "walk",
            "sub_mode": "ingredients",
            "reference_image_path": "a.png",
            "reference_image_paths": ["a.png", "b.png"],
            "dry_run": True,
        },
    )
    manager._run_node_video(job)

    assert job.state == "succeeded"
    assert seen["reference_image_path"] == "a.png"
    assert seen["reference_image_paths"] == ["a.png", "b.png"]


def test_node_image_job_forwards_model_and_count(tmp_path):
    seen: dict = {}

    class RecordingService(FakeService):
        def generate_image(self, **kwargs):
            seen.update(kwargs)
            return NodeImageResult(
                status="dry_run",
                prompt="x",
                aspect_ratio="1:1",
                aspect_enum=1,
                run_id="r1",
                run_dir=str(tmp_path / "r1"),
                model="nano_banana_pro",
                count=3,
                agent_mode=True,
            )

    manager = _manager(tmp_path, RecordingService())
    job = Job(
        "node_image",
        {
            "prompt": "x",
            "aspect_ratio": "1:1",
            "aspect": 1,
            "model": "nano_banana_pro",
            "count": 3,
            "agent_mode": True,
            "dry_run": True,
        },
    )
    manager._run_node_image(job)

    assert job.state == "succeeded"
    assert seen["model"] == "nano_banana_pro"
    assert seen["count"] == 3
    assert seen["agent_mode"] is True
    assert job.result["count"] == 3
    assert job.result["agent_mode"] is True
