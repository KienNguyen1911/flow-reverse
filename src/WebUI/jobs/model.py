"""Job record + event log: the unit the API polls (``/api/jobs/{id}``)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

TERMINAL_STATES = {"succeeded", "failed", "rejected"}


@dataclass
class JobEvent:
    ts_ms: int
    kind: str
    message: str
    data: dict = field(default_factory=dict)


class Job:
    def __init__(self, kind: str, params: dict):
        self.id = "j_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.kind = kind
        self.params = params
        self.state = "queued"          # queued | running | succeeded | failed | rejected
        self.events: list[JobEvent] = []
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.created_ms = int(time.time() * 1000)
        self.started_ms: Optional[int] = None
        self.finished_ms: Optional[int] = None
        #: Set when the user stops the run; long waits (e.g. retry backoff) poll it.
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()

    # -- cancellation --------------------------------------------------------- #

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def cancel(self, reason: str = "") -> None:
        """Ask the running job to stop; interruptible waits abort immediately."""
        self.cancel_event.set()
        self.add_event("warn", reason or "Đã yêu cầu dừng job — hủy các bước đang chờ…")


    def add_event(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        with self._lock:
            self.events.append(JobEvent(ts_ms=int(time.time() * 1000), kind=kind, message=message, data=data or {}))
            if len(self.events) > 800:
                del self.events[:100]

    def set_state(self, state: str) -> None:
        with self._lock:
            self.state = state

    def to_dict(self, with_events: bool = True) -> dict:
        with self._lock:
            d = {
                "id": self.id,
                "kind": self.kind,
                "params": self.params,
                "state": self.state,
                "created_ms": self.created_ms,
                "started_ms": self.started_ms,
                "finished_ms": self.finished_ms,
                "result": self.result,
                "error": self.error,
                "event_count": len(self.events),
            }
            if with_events:
                d["events"] = [
                    {"i": i, "ts_ms": e.ts_ms, "kind": e.kind, "message": e.message, "data": e.data}
                    for i, e in enumerate(self.events)
                ]
            return d
