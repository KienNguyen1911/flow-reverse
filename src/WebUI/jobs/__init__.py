"""Job layer for the Flow Bench playground (N-account pool edition).

Package layout:

  model.py             Job / JobEvent (what the API polls)
  projects_store.py    ProjectsStore (out/playground_projects.json registry)
  batch.py             batch_generate: item planning + BatchRunner
  runners_single.py    generate / dry_run / list_projects / create_project
  runners_node.py      node_image / node_video / node_last_frame
  runners_workflow.py  auto_tryon / delivery_build
  manager.py           JobManager: queue, dispatcher thread, account/project helpers

This ``__init__`` re-exports the public names so ``from src.WebUI.jobs import X``
keeps working for callers, tests and scripts.
"""

from ...Workflows.node_retry import NodeExecutionError, RetryAborted
from ..settings import ROOT
from .batch import (
    MAX_BATCH_ITEMS,
    BatchItem,
    BatchRunner,
    plan_dependency_waves,
    prepare_batch_items,
)
from .manager import JobManager
from .model import TERMINAL_STATES, Job, JobEvent
from .projects_store import ProjectsStore

__all__ = [
    "MAX_BATCH_ITEMS",
    "ROOT",
    "TERMINAL_STATES",
    "BatchItem",
    "BatchRunner",
    "Job",
    "JobEvent",
    "JobManager",
    "NodeExecutionError",
    "ProjectsStore",
    "RetryAborted",
    "plan_dependency_waves",
    "prepare_batch_items",
]
