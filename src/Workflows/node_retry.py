"""Node-level auto-retry for Google Flow anti-abuse rejections (Task 3).

Flow sometimes answers a *valid* generation request with
``PUBLIC_ERROR_UNUSUAL_ACTIVITY`` (gRPC 7 / PERMISSION_DENIED, 0 credit). It is
a rate/behaviour signal, not a broken request: the exact same payload usually
succeeds a little later. Retrying at the node boundary therefore recovers work
without spending credit (a rejection costs nothing).

Policy (per requirement):

    * image node → retry 1 after 10 s, retry 2 after 20 s
    * video node → retry 1 after 30 s, retry 2 after 60 s
    * any other error → propagates immediately (no retry)
    * after both retries still rejected → :class:`NodeExecutionError`
      (``EXECUTION_ERROR``) is raised, and the node fails as before.

Every attempt is logged through the node's job event log so the UI drawer shows
the waiting state. Waiting is interruptible: the caller passes the job's cancel
event and the countdown aborts within ~250 ms when the user stops the run.

Usage::

    res = run_with_retry(
        lambda: svc.generate_video(...),
        kind="video",
        log=job.add_event,
        abort=job.cancel_event,
    )
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

#: Marker Google returns for anti-abuse rejections (see flow_bridge.describe_reject).
UNUSUAL_ACTIVITY_CODE = "PUBLIC_ERROR_UNUSUAL_ACTIVITY"
EXECUTION_ERROR_CODE = "EXECUTION_ERROR"

#: Backoff schedule per node kind (1-based retry → delay in seconds).
RETRY_DELAYS_S: dict[str, tuple[float, ...]] = {
    "image": (10.0, 20.0),
    "video": (30.0, 60.0),
}

#: Vietnamese labels used in the human-readable retry log lines.
_KIND_LABELS: dict[str, str] = {
    "image": "tạo ảnh",
    "video": "tạo video",
}

_POLL_S = 0.25


class RetryAborted(RuntimeError):
    """The wait was cancelled (user stopped the flow) before the next attempt."""

    code = "EXECUTION_CANCELLED"


class NodeExecutionError(RuntimeError):
    """Node failed permanently after exhausting the anti-abuse retry budget."""

    code = EXECUTION_ERROR_CODE

    def __init__(self, message: str, *, code: str = EXECUTION_ERROR_CODE,
                 attempts: int = 0, reason: Optional[str] = None,
                 hint: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.attempts = attempts
        self.reason = reason
        self.hint = hint


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


def _text_of(value: Any) -> str:
    """Flatten the string-ish fields of a result object/dict/exception."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, BaseException):
        parts = [str(value), *(str(a) for a in value.args if a is not None)]
        return " ".join(parts)
    if isinstance(value, dict):
        keys = ("status", "reason", "hint", "detail", "error", "message", "code")
        return " ".join(str(value.get(k) or "") for k in keys)
    keys = ("status", "reason", "hint", "detail", "error", "message", "code")
    return " ".join(str(getattr(value, k, "") or "") for k in keys)


def is_unusual_activity(value: Any) -> bool:
    """True when *value* is a flow result/exception caused by anti-abuse.

    A result counts only when it is a rejection/failure: a successful result
    that merely mentions the marker (e.g. echoed metadata) must never retry.
    """
    text = _text_of(value)
    if UNUSUAL_ACTIVITY_CODE not in text:
        # No marker: accept the gRPC-7/anti_abuse signal on rejected results.
        status = _field(value, "status")
        if status not in ("rejected", "failed"):
            return False
        if _field(value, "grpc_code") == 7:
            return True
        return bool(_field(value, "anti_abuse")) or "PERMISSION_DENIED" in text

    status = _field(value, "status")
    if status is None:
        # Exceptions / raw strings carry no status → the marker alone decides.
        return True
    return status in ("rejected", "failed")


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


# --------------------------------------------------------------------------- #
# Interruptible wait
# --------------------------------------------------------------------------- #


def _sleep_interruptible(seconds: float, abort: Optional[threading.Event],
                         on_tick: Optional[Callable[[float], None]] = None) -> bool:
    """Sleep *seconds*; return False as soon as *abort* is set."""
    if seconds <= 0:
        return not (abort is not None and abort.is_set())
    deadline = time.monotonic() + float(seconds)
    last_tick = -1
    while True:
        if abort is not None and abort.is_set():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        if on_tick is not None:
            secs = int(remaining)
            if secs != last_tick:
                last_tick = secs
                on_tick(remaining)
        time.sleep(min(_POLL_S, remaining))


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def delay_schedule(kind: str) -> tuple[float, ...]:
    return RETRY_DELAYS_S.get(str(kind or "").lower(), ())


def run_with_retry(
    fn: Callable[[], T],
    *,
    kind: str,
    log: Optional[Callable[..., None]] = None,
    abort: Optional[threading.Event] = None,
    delays: Optional[tuple[float, ...]] = None,
) -> T:
    """Call *fn* with the anti-abuse retry policy for *kind* ("image"|"video").

    ``log`` uses the :class:`~src.WebUI.jobs.Job.add_event` signature
    ``(kind, message, data)``; a 2-arg logger is tolerated.

    Raises :class:`RetryAborted` when cancelled mid-wait and
    :class:`NodeExecutionError` when the budget is exhausted.
    """
    schedule = delay_schedule(kind) if delays is None else tuple(delays)
    label = _KIND_LABELS.get(str(kind or "").lower(), "thực thi node")

    def emit(level: str, message: str, data: Optional[dict] = None) -> None:
        if log is None:
            return
        try:
            log(level, message, data or {})
        except TypeError:
            try:
                log(level, message)
            except Exception:  # noqa: BLE001 - logging must never break the run
                pass
        except Exception:  # noqa: BLE001
            pass

    attempts_done = 0
    while True:
        failure: Any = None
        try:
            result = fn()
        except (RetryAborted, KeyboardInterrupt):
            raise
        except Exception as exc:  # noqa: BLE001 - classified below
            if not is_unusual_activity(exc):
                raise
            result = None
            failure = exc
        else:
            if not is_unusual_activity(result):
                return result
            failure = result

        attempts_done += 1
        retry_no = attempts_done               # 1-based; retry #1 follows failure #1
        if retry_no > len(schedule):
            detail = str(failure) if failure is not None else "không rõ"
            hint = _field(failure, "hint") or ""
            raise NodeExecutionError(
                f"Vẫn bị hệ thống chống lạm dụng từ chối ({UNUSUAL_ACTIVITY_CODE}) sau "
                f"{len(schedule)} lần thử lại khi {label}. {hint}".strip(),
                attempts=attempts_done,
                reason=_field(failure, "reason") or "PERMISSION_DENIED",
                hint=hint or None,
            ) from (failure if isinstance(failure, BaseException) else None)

        wait_s = float(schedule[retry_no - 1])
        emit(
            "retry",
            f"[Retry {retry_no}/{len(schedule)}] Gặp lỗi {UNUSUAL_ACTIVITY_CODE} khi {label}. "
            f"Đang chờ {wait_s:.0f}s trước khi thử lại...",
            {
                "code": UNUSUAL_ACTIVITY_CODE,
                "attempt": retry_no,
                "max_attempts": len(schedule),
                "delay_s": wait_s,
                "kind": kind,
            },
        )
        started = time.monotonic()
        finished = _sleep_interruptible(wait_s, abort)
        if abort is not None and abort.is_set():
            emit(
                "warn",
                f"[Retry {retry_no}/{len(schedule)}] Đã hủy chờ (người dùng dừng luồng) — "
                f"không thử lại khi {label}.",
                {"code": UNUSUAL_ACTIVITY_CODE, "attempt": retry_no, "cancelled": True},
            )
            raise RetryAborted(f"Đã hủy retry {retry_no}/{len(schedule)} khi {label}")
        if not finished:  # pragma: no cover - covered by the abort branch above
            raise RetryAborted(f"Đã hủy retry {retry_no}/{len(schedule)} khi {label}")
        emit(
            "info",
            f"[Retry {retry_no}/{len(schedule)}] Hết thời gian chờ "
            f"({time.monotonic() - started:.0f}s) — thử lại {label}...",
            {"code": UNUSUAL_ACTIVITY_CODE, "attempt": retry_no},
        )


__all__ = [
    "EXECUTION_ERROR_CODE",
    "NodeExecutionError",
    "RETRY_DELAYS_S",
    "RetryAborted",
    "UNUSUAL_ACTIVITY_CODE",
    "delay_schedule",
    "is_unusual_activity",
    "run_with_retry",
]
