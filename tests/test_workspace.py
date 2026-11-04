"""Workspace project + project-scoped asset tests (no browser required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.WebUI.app import create_app
from src.WebUI.workspace import DEFAULT_PROJECT_NAME


def make_client(base: Path) -> TestClient:
    app = create_app(
        out_dir=base / "playground",
        projects_file=base / "projects.json",
        pool_config=base / "pool.json",
        pool_state=base / "pool_state.json",
        web_dist=base / "dist",
    )
    return TestClient(app)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return make_client(tmp_path)


def default_project(client: TestClient) -> dict:
    projects = client.get("/api/workspace/projects").json()["projects"]
    assert projects
    return projects[0]


def test_starts_with_default_project(client: TestClient):
    projects = client.get("/api/workspace/projects").json()["projects"]
    assert len(projects) == 1
    project = projects[0]
    assert project["name"] == DEFAULT_PROJECT_NAME
    assert project["canvasState"]["viewport"] == {"x": 40.0, "y": 20.0, "zoom": 1.0}
    assert project["canvasState"]["nodes"] == []
    assert project["canvasState"]["edges"] == []
    assert project["canvasState"]["groups"] == []
    assert project["nodeCount"] == 0


def test_canvas_roundtrip_keeps_viewport_nodes_edges_groups(client: TestClient):
    project = default_project(client)
    pid = project["id"]
    canvas = {
        "viewport": {"x": -120, "y": 45, "zoom": 0.72},
        "nodes": [
            {
                "id": "ref_1",
                "type": "ref",
                "x": 10,
                "y": 20,
                "prompt": "",
                "status": "succeeded",
                "fileUrl": "/api/uploads/a.png",
            },
            {
                "id": "image_1",
                "type": "image",
                "x": 340,
                "y": 20,
                "prompt": "lookbook",
                "seed": 42,
                "aspectRatio": "9:16",
                "status": "succeeded",
                "sourceImageId": "ref_1",
            },
        ],
        "edges": [{"id": "e1", "source": "ref_1", "target": "image_1"}],
        "groups": [{"id": "g1", "name": "Nhóm 1", "nodeIds": ["ref_1", "image_1"]}],
    }
    r = client.put(f"/api/workspace/projects/{pid}/canvas", json=canvas)
    assert r.status_code == 200
    assert r.json()["projectId"] == pid

    full = client.get(f"/api/workspace/projects/{pid}").json()["project"]
    assert full["canvasState"]["viewport"] == {"x": -120.0, "y": 45.0, "zoom": 0.72}
    assert [n["id"] for n in full["canvasState"]["nodes"]] == ["ref_1", "image_1"]
    assert full["canvasState"]["nodes"][1]["seed"] == 42
    assert full["canvasState"]["edges"] == canvas["edges"]
    assert full["canvasState"]["groups"] == canvas["groups"]

    listed = client.get("/api/workspace/projects").json()["projects"]
    entry = next(p for p in listed if p["id"] == pid)
    assert entry["nodeCount"] == 2


def test_project_crud_and_last_project_guard(client: TestClient):
    base = default_project(client)

    created = client.post(
        "/api/workspace/projects",
        json={
            "name": "Lookbook Thu Đông",
            "canvasState": {
                "viewport": {"x": 0, "y": 0, "zoom": 1},
                "nodes": [
                    {
                        "id": "image_1",
                        "type": "image",
                        "x": 0,
                        "y": 0,
                        "prompt": "coat",
                        "status": "idle",
                    }
                ],
                "edges": [],
                "groups": [],
            },
        },
    )
    assert created.status_code == 200
    project = created.json()["project"]
    assert project["name"] == "Lookbook Thu Đông"
    assert project["canvasState"]["nodes"][0]["prompt"] == "coat"

    renamed = client.patch(
        f"/api/workspace/projects/{project['id']}", json={"name": "Lookbook Đông"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["project"]["name"] == "Lookbook Đông"

    dup = client.post(f"/api/workspace/projects/{project['id']}/duplicate", json={})
    assert dup.status_code == 200
    dup_project = dup.json()["project"]
    assert dup_project["name"].endswith("(Bản sao)")
    assert dup_project["canvasState"]["nodes"][0]["prompt"] == "coat"

    assert client.delete(f"/api/workspace/projects/{dup_project['id']}").status_code == 200
    assert client.delete(f"/api/workspace/projects/{project['id']}").status_code == 200
    # The default project is the last one and must be protected.
    assert client.delete(f"/api/workspace/projects/{base['id']}").status_code == 400


def test_canvas_state_is_isolated_per_project(client: TestClient):
    first = default_project(client)["id"]
    second = client.post("/api/workspace/projects", json={"name": "Project 2"}).json()["project"]["id"]

    canvas_a = {
        "viewport": {"x": 1, "y": 2, "zoom": 1.5},
        "nodes": [{"id": "a1", "type": "image", "x": 0, "y": 0, "prompt": "A", "status": "idle"}],
        "edges": [],
        "groups": [],
    }
    canvas_b = {
        "viewport": {"x": 9, "y": 8, "zoom": 0.5},
        "nodes": [{"id": "b1", "type": "video", "x": 5, "y": 6, "prompt": "B", "status": "idle"}],
        "edges": [],
        "groups": [{"id": "gb", "name": "Nhóm B", "nodeIds": ["b1"]}],
    }
    assert client.put(f"/api/workspace/projects/{first}/canvas", json=canvas_a).status_code == 200
    assert client.put(f"/api/workspace/projects/{second}/canvas", json=canvas_b).status_code == 200

    left = client.get(f"/api/workspace/projects/{first}").json()["project"]["canvasState"]
    right = client.get(f"/api/workspace/projects/{second}").json()["project"]["canvasState"]
    assert left["nodes"][0]["prompt"] == "A"
    assert left["viewport"]["zoom"] == 1.5
    assert right["nodes"][0]["prompt"] == "B"
    assert right["viewport"] == {"x": 9.0, "y": 8.0, "zoom": 0.5}
    assert right["groups"][0]["nodeIds"] == ["b1"]


def test_thumbnail_manual_override_and_clear(client: TestClient):
    pid = default_project(client)["id"]

    # A project with no media keeps a null auto thumbnail.
    assert default_project(client)["thumbnailUrl"] is None

    # Upload inside the project -> auto thumbnail comes from the latest media.
    files = {"file": ("cover.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    up = client.post("/api/upload", files=files, data={"project_id": pid}).json()
    listed = next(p for p in client.get("/api/workspace/projects").json()["projects"] if p["id"] == pid)
    assert listed["thumbnailUrl"] == up["url"]
    assert listed["thumbnailManual"] is False

    # A manual pick wins over the automatic one.
    r = client.put(
        f"/api/workspace/projects/{pid}/thumbnail",
        json={"thumbnailUrl": "/api/uploads/chosen.png"},
    )
    assert r.status_code == 200
    assert r.json()["thumbnailUrl"] == "/api/uploads/chosen.png"
    assert r.json()["thumbnailManual"] is True
    listed = next(p for p in client.get("/api/workspace/projects").json()["projects"] if p["id"] == pid)
    assert listed["thumbnailUrl"] == "/api/uploads/chosen.png"
    assert listed["thumbnailManual"] is True

    # Clearing returns control to the automatic latest-media thumbnail.
    r = client.put(f"/api/workspace/projects/{pid}/thumbnail", json={"thumbnailUrl": None})
    assert r.status_code == 200
    assert r.json()["thumbnailManual"] is False
    listed = next(p for p in client.get("/api/workspace/projects").json()["projects"] if p["id"] == pid)
    assert listed["thumbnailUrl"] == up["url"]

    # Duplicating carries the manual choice across.
    client.put(
        f"/api/workspace/projects/{pid}/thumbnail",
        json={"thumbnailUrl": "/api/uploads/chosen.png"},
    )
    dup = client.post(f"/api/workspace/projects/{pid}/duplicate", json={}).json()["project"]
    assert dup["thumbnailUrl"] == "/api/uploads/chosen.png"
    assert dup["thumbnailManual"] is True

    assert client.put("/api/workspace/projects/nope/thumbnail", json={"thumbnailUrl": "x"}).status_code == 404


def test_migration_endpoint_only_imports_canvas_once(client: TestClient):
    """A stale browser tab must not overwrite a wiped/curated canvas."""
    pid = default_project(client)["id"]
    canvas = {
        "viewport": {"x": 1, "y": 2, "zoom": 1},
        "nodes": [{"id": "n1", "type": "image", "x": 0, "y": 0, "prompt": "old", "status": "idle"}],
        "edges": [],
        "groups": [],
    }
    first = client.post("/api/workspace/migrate", json={"canvasState": canvas}).json()
    assert first["canvasImported"] is True

    # The user wipes the canvas server-side.
    client.put(
        f"/api/workspace/projects/{pid}/canvas",
        json={"viewport": {"x": 0, "y": 0, "zoom": 1}, "nodes": [], "edges": [], "groups": []},
    )

    # A stale client re-posting its old localStorage graph must be ignored.
    second = client.post("/api/workspace/migrate", json={"canvasState": canvas}).json()
    assert second["canvasImported"] is False
    current = client.get(f"/api/workspace/projects/{pid}").json()["project"]["canvasState"]
    assert current["nodes"] == []
    assert client.get("/api/workspace/projects").json()["legacyMigrated"] is True


def test_upload_binding_and_project_scope(client: TestClient):
    first = default_project(client)["id"]
    second = client.post("/api/workspace/projects", json={"name": "Project 2"}).json()["project"]["id"]

    files = {"file": ("model.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    up = client.post("/api/upload", files=files, data={"project_id": first})
    assert up.status_code == 200
    assert up.json()["projectId"] == first
    name = up.json()["filename"]

    scoped = client.get(
        "/api/assets/uploaded", params={"project_id": first, "scope": "project"}
    ).json()["items"]
    assert [i["name"] for i in scoped] == [name]
    assert scoped[0]["projectId"] == first
    assert scoped[0]["key"] == f"upload:{name}"

    other = client.get(
        "/api/assets/uploaded", params={"project_id": second, "scope": "project"}
    ).json()["items"]
    assert other == []

    # Pinned assets stay visible in every project.
    pin = client.post(
        "/api/assets/pin", json={"key": f"upload:{name}", "isPinned": True}
    )
    assert pin.status_code == 200 and pin.json()["isPinned"] is True
    pinned_elsewhere = client.get(
        "/api/assets/uploaded", params={"project_id": second, "scope": "project"}
    ).json()["items"]
    assert [i["name"] for i in pinned_elsewhere] == [name]
    assert pinned_elsewhere[0]["isPinned"] is True

    all_items = client.get("/api/assets/uploaded", params={"scope": "all"}).json()["items"]
    assert [i["name"] for i in all_items] == [name]
    assert all_items[0]["projectName"] == DEFAULT_PROJECT_NAME


def test_startup_migration_claims_existing_media(tmp_path: Path):
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "1700000000000_legacy.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    gallery = tmp_path / "playground" / "run_legacy"
    gallery.mkdir(parents=True)
    (gallery / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (gallery / "meta.json").write_text(
        json.dumps(
            {
                "file": str(gallery / "image.png"),
                "prompt": "legacy gallery run",
                "created_ts": "2026-01-01T00:00:00",
                "status": "ok",
            }
        ),
        encoding="utf-8",
    )

    client = make_client(tmp_path)
    projects = client.get("/api/workspace/projects").json()["projects"]
    assert len(projects) == 1
    pid = projects[0]["id"]

    uploaded = client.get("/api/assets/uploaded").json()["items"]
    legacy = next(i for i in uploaded if i["name"] == "1700000000000_legacy.png")
    assert legacy["projectId"] == pid

    runs = client.get("/api/gallery").json()["runs"]
    run = next(r for r in runs if r["run"] == "run_legacy")
    assert run["workspace_project_id"] == pid

    # Counts on the project payload include claimed media.
    summary = client.get("/api/workspace/projects").json()["projects"][0]
    assert summary["assetCount"] >= 2


def test_migrate_endpoint_restores_legacy_canvas_and_pins(client: TestClient):
    pid = default_project(client)["id"]
    canvas = {
        "viewport": {"x": 12, "y": 34, "zoom": 1.2},
        "nodes": [{"id": "n1", "type": "image", "x": 1, "y": 2, "prompt": "legacy", "status": "idle"}],
        "edges": [],
        "groups": [],
    }
    r = client.post(
        "/api/workspace/migrate",
        json={"name": DEFAULT_PROJECT_NAME, "canvasState": canvas, "pinnedIds": ["legacy.png"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["project"]["id"] == pid
    assert body["project"]["canvasState"]["nodes"][0]["prompt"] == "legacy"

    uploads = client.get("/api/assets/uploaded").json()["items"]
    # No file exists for the legacy pin, but the pin itself is persisted.
    assert uploads == []
    meta = json.loads((Path(client.app.state.out_root).parent / "flowbench_asset_meta.json").read_text(encoding="utf-8"))
    assert meta["assets"]["upload:legacy.png"]["isPinned"] is True


def test_workspace_flow_projects_mapping_and_persistence(tmp_path: Path):
    from src.WebUI.workspace import WorkspaceStore

    ws_file = tmp_path / "flowbench_workspace.json"
    store = WorkspaceStore(ws_file)
    project = store.create("Test Flow Projects")

    # Initially empty
    assert store.get_flow_project(project.id, "flow_main") is None
    assert project.flow_projects == {}

    # Set flow project mapping
    store.set_flow_project(project.id, "flow_main", "c1f7b7e5-1234-5678-abcd-000000000001")
    store.set_flow_project(project.id, "flow_acc2", "c1f7b7e5-1234-5678-abcd-000000000002")

    assert store.get_flow_project(project.id, "flow_main") == "c1f7b7e5-1234-5678-abcd-000000000001"
    assert store.get_flow_project(project.id, "flow_acc2") == "c1f7b7e5-1234-5678-abcd-000000000002"

    # Reload from disk to verify persistence
    reloaded_store = WorkspaceStore(ws_file)
    reloaded_proj = reloaded_store.get(project.id)
    assert reloaded_proj is not None
    assert reloaded_proj.flow_projects["flow_main"] == "c1f7b7e5-1234-5678-abcd-000000000001"
    assert reloaded_proj.flow_projects["flow_acc2"] == "c1f7b7e5-1234-5678-abcd-000000000002"
    assert reloaded_store.get_flow_project(project.id, "flow_main") == "c1f7b7e5-1234-5678-abcd-000000000001"

    # Remove flow project mapping
    assert reloaded_store.remove_flow_project(project.id, "flow_main") is True
    assert reloaded_store.get_flow_project(project.id, "flow_main") is None
    assert reloaded_store.remove_flow_project(project.id, "non_existent") is False


def test_workspace_canvas_save_keeps_flow_projects(client: TestClient):
    workspace = client.app.state.workspace
    project = default_project(client)
    pid = project["id"]

    # Set a flow project on default project
    workspace.set_flow_project(pid, "flow_main", "c1f7b7e5-1234-5678-abcd-000000000001")
    assert workspace.get_flow_project(pid, "flow_main") == "c1f7b7e5-1234-5678-abcd-000000000001"

    # Frontend autosaves canvas via API
    canvas = {
        "viewport": {"x": 50, "y": 50, "zoom": 1.0},
        "nodes": [{"id": "n1", "type": "image", "x": 10, "y": 10, "prompt": "hi"}],
        "edges": [],
        "groups": [],
    }
    r = client.post(f"/api/workspace/projects/{pid}/canvas", json=canvas)
    assert r.status_code == 200

    # Flow projects mapping must be preserved!
    assert workspace.get_flow_project(pid, "flow_main") == "c1f7b7e5-1234-5678-abcd-000000000001"
    full = client.get(f"/api/workspace/projects/{pid}").json()["project"]
    assert full.get("flowProjects", {}).get("flow_main") == "c1f7b7e5-1234-5678-abcd-000000000001"
