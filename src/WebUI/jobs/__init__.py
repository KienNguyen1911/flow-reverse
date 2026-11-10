"""Job layer for the Flow Bench playground (N-account pool edition).

Package layout:

  model.py             Job / JobEvent (what the API polls)
  runners_node.py      node_image / node_video / node_last_frame
  runners_workflow.py  delivery_build
  manager.py           JobManager: queue, dispatcher thread, account helpers

This ``__init__`` re-exports the public names so ``from src.WebUI.jobs import X``
keeps working for callers and tests.
"""

from ...Workflows.node_retry import NodeExecutionError, RetryAborted
from ..settings import ROOT
from .manager import JobManager
from .model import TERMINAL_STATES, Job, JobEvent

__all__ = [
    "ROOT",
    "TERMINAL_STATES",
    "Job",
    "JobEvent",
    "JobManager",
    "NodeExecutionError",
    "RetryAborted",
]
