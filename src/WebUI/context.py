"""Server-side state shared by every route module.

:func:`build_context` wires the stores, the account pool and the job manager once
per app (``create_app``) and runs the one-time workspace migration. Route modules
receive the resulting :class:`AppContext` and close over what they need.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..Workflows.account_pool import AccountPoolManager
from ..Workflows.flow_client import DEFAULT_CDP_URL
from .asset_scan import migration_asset_entries
from .jobs import JobManager, ProjectsStore
from .settings import DEFAULT_OUT, DEFAULT_PROJECTS_FILE, ROOT
from .workspace import DEFAULT_PROJECT_NAME, AssetMetaStore, WorkspaceStore


@dataclass
class AppContext:
    pool: AccountPoolManager
    manager: JobManager
    store: ProjectsStore
    workspace: WorkspaceStore
    asset_meta: AssetMetaStore
    out_root: Path
    #: The ``out_dir`` argument exactly as passed to ``create_app`` (``None`` = defaults).
    out_dir: Optional[Path]
    #: Where ``uploads/`` and ``references/`` live.
    asset_root: Path
    delivery_root: Optional[Path]


def build_context(
    cdp_url: str = DEFAULT_CDP_URL,
    out_dir: Optional[Path] = None,
    projects_file: Optional[Path] = None,
    pool_config: Optional[Path] = None,
    pool_state: Optional[Path] = None,
    workspace_file: Optional[Path] = None,
    asset_meta_file: Optional[Path] = None,
    delivery_root: Optional[Path] = None,
) -> AppContext:
    out_root = Path(out_dir) if out_dir else DEFAULT_OUT
    asset_root = out_root.parent if out_dir else (ROOT / "out")
    store = ProjectsStore(Path(projects_file) if projects_file else DEFAULT_PROJECTS_FILE)
    workspace = WorkspaceStore(
        Path(workspace_file) if workspace_file else (out_root.parent / "flowbench_workspace.json")
    )
    asset_meta = AssetMetaStore(
        Path(asset_meta_file) if asset_meta_file else (out_root.parent / "flowbench_asset_meta.json")
    )
    pool = AccountPoolManager(
        config_path=Path(pool_config) if pool_config else None,
        state_path=Path(pool_state) if pool_state else None,
        out_root=out_root,
        default_cdp_url=cdp_url,
    )
    manager = JobManager(pool=pool, store=store, out_root=out_root)
    manager.asset_meta = asset_meta
    manager.workspace = workspace

    # One-time migration: with no workspace project, create the default one and
    # claim every pre-existing asset so no upload/output is lost.
    if workspace.count() == 0:
        default_project = workspace.create(DEFAULT_PROJECT_NAME)
        asset_meta.claim_unassigned(
            migration_asset_entries(out_dir, out_root, manager.node_out, asset_meta),
            default_project.id,
        )
    else:
        # An existing store means the one-time browser import already happened;
        # never re-import stale client canvas data over server-side truth.
        workspace.mark_legacy_migrated()

    return AppContext(
        pool=pool,
        manager=manager,
        store=store,
        workspace=workspace,
        asset_meta=asset_meta,
        out_root=out_root,
        out_dir=out_dir,
        asset_root=asset_root,
        delivery_root=delivery_root,
    )
