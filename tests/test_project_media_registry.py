import pytest
from pathlib import Path
from src.Workflows.project_media_registry import (
    ProjectMediaRegistry,
    compute_alias_name,
)


def test_compute_alias_name():
    assert compute_alias_name(0, "a1b2c3d4e5f6") == "model_a1b2c3"
    assert compute_alias_name(1, "d4e5f6789abc") == "garment_d4e5f6"
    assert compute_alias_name(2, "789abcdef012") == "scene_789abc"
    assert compute_alias_name(3, "112233445566") == "ref4_112233"
    assert compute_alias_name(4, "998877665544") == "ref5_998877"


def test_project_media_registry_crud(tmp_path: Path):
    cache_file = tmp_path / "project_media_cache.json"
    reg = ProjectMediaRegistry(cache_file)

    # 1. Initial lookup is None
    assert reg.get("acc_1", "proj_1", "sha_abc") is None

    # 2. Put entry
    saved = reg.put("acc_1", "proj_1", "sha_abc", "media_uuid_1", "model_abc")
    assert saved["media_id"] == "media_uuid_1"
    assert saved["alias_name"] == "model_abc"

    # 3. Get entry
    found = reg.get("acc_1", "proj_1", "sha_abc")
    assert found is not None
    assert found["media_id"] == "media_uuid_1"
    assert found["alias_name"] == "model_abc"

    # 4. Count for project
    reg.put("acc_1", "proj_1", "sha_xyz", "media_uuid_2", "garment_xyz")
    reg.put("acc_1", "proj_2", "sha_xyz", "media_uuid_3", "garment_xyz")
    assert reg.count_for_project("acc_1", "proj_1") == 2
    assert reg.count_for_project("acc_1", "proj_2") == 1

    # 5. Persistence across instances
    reg2 = ProjectMediaRegistry(cache_file)
    assert reg2.get("acc_1", "proj_1", "sha_abc")["media_id"] == "media_uuid_1"

    # 6. Remove entry
    removed = reg.remove("acc_1", "proj_1", "sha_abc")
    assert removed is not None
    assert reg.get("acc_1", "proj_1", "sha_abc") is None

    # 7. Clear project
    cleared = reg.clear_project("acc_1", "proj_1")
    assert cleared == 1  # only sha_xyz was left in proj_1
    assert reg.count_for_project("acc_1", "proj_1") == 0
    # proj_2 untouched
    assert reg.count_for_project("acc_1", "proj_2") == 1
