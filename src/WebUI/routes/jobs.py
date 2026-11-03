"""Bridge/queue status and the job list/detail/cancel endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..context import AppContext

def build_router(ctx: AppContext) -> APIRouter:
    pool = ctx.pool
    manager = ctx.manager
    router = APIRouter()

    @router.get("/api/status")
    def api_status():
        client = pool.status_client()
        st = client.status()
        snap = client.breaker.snapshot()
        d = st.model_dump()
        d["queue_depth"] = manager.queue_depth()
        d["current_job_id"] = manager.current_id()
        d["breaker"] = {
            "cooldown_remaining_s": snap.get("cooldown_remaining_s"),
            "cooldown_reason": snap.get("cooldown_reason") or None,
            "total_accepted": snap.get("total_accepted"),
            "total_rejected": snap.get("total_rejected"),
            "consecutive_anti_abuse": snap.get("consecutive_anti_abuse"),
        }
        return d

    @router.get("/api/jobs")
    def api_jobs(limit: int = 30):
        return {"jobs": [j.to_dict(with_events=False) for j in manager.list(limit=limit)]}

    @router.get("/api/jobs/{jid}")
    def api_job(jid: str):
        job = manager.get(jid)
        if job is None:
            raise HTTPException(status_code=404, detail="job không tồn tại")
        return job.to_dict(with_events=True)

    @router.post("/api/jobs/{jid}/cancel")
    def api_cancel_job(jid: str):
        """Stop a running job; interruptible waits (retry backoff) abort at once."""
        job = manager.get(jid)
        if job is None:
            raise HTTPException(status_code=404, detail="job không tồn tại")
        if job.state in ("succeeded", "failed", "rejected"):
            return {"ok": True, "state": job.state, "note": "job đã kết thúc"}
        job.cancel()
        return {"ok": True, "state": job.state, "cancelled": True}

    return router
