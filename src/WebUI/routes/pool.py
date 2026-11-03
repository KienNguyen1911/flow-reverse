"""Account pool: working set vs standby, per-account actions, circuit reset."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...Workflows.account_pool import proxy_label
from ..context import AppContext

class PoolConfigBody(BaseModel):
    target_jobs_per_account: Optional[int] = None
    max_active_browsers: Optional[int] = None


class AddAccountBody(BaseModel):
    id: str
    profile_id: Optional[str] = None
    cdp_port: Optional[int] = None
    enabled: bool = True
    note: Optional[str] = None
    create_profile: bool = True
    proxy: Optional[str] = None          # "" / null ⇒ direct IP
    proxy_bypass: Optional[str] = None


class UpdateAccountBody(BaseModel):
    enabled: Optional[bool] = None
    note: Optional[str] = None
    cdp_port: Optional[int] = None
    proxy: Optional[str] = None
    proxy_bypass: Optional[str] = None
    clear_proxy: bool = False


def build_router(ctx: AppContext) -> APIRouter:
    pool = ctx.pool
    router = APIRouter()

    @router.get("/api/pool")
    def api_pool():
        return pool.snapshot()

    @router.post("/api/pool/config")
    def api_pool_config(body: PoolConfigBody):
        try:
            updated = pool.update_config(body.target_jobs_per_account, body.max_active_browsers)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, **updated}

    @router.post("/api/pool/accounts/{aid}/wake")
    def api_pool_wake(aid: str):
        try:
            return pool.wake_account(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/api/pool/accounts/{aid}/hibernate")
    def api_pool_hibernate(aid: str):
        try:
            return pool.hibernate_account(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/api/pool/accounts/{aid}/reset")
    def api_pool_reset(aid: str):
        try:
            return pool.reset_account(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/api/pool/next_port")
    def api_pool_next_port():
        return {"next_port": pool.next_suggested_port()}

    @router.post("/api/pool/accounts")
    def api_pool_add_account(body: AddAccountBody):
        try:
            acc = pool.add_account(
                account_id=body.id,
                profile_id=body.profile_id,
                cdp_port=body.cdp_port,
                enabled=body.enabled,
                note=body.note or "",
                create_profile=body.create_profile,
                proxy=body.proxy,
                proxy_bypass=body.proxy_bypass,
            )
            return {
                "ok": True,
                "account": {
                    "id": acc.id,
                    "profile_id": acc.profile_id,
                    "cdp_port": acc.cdp_port,
                    "enabled": acc.enabled,
                    "note": acc.note,
                    "proxy": proxy_label(acc.proxy),
                    "has_proxy": bool(acc.proxy),
                },
            }
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.patch("/api/pool/accounts/{aid}")
    def api_pool_update_account(aid: str, body: UpdateAccountBody):
        try:
            acc = pool.update_account(
                account_id=aid,
                enabled=body.enabled,
                note=body.note,
                cdp_port=body.cdp_port,
                proxy=body.proxy,
                proxy_bypass=body.proxy_bypass,
                clear_proxy=body.clear_proxy,
            )
            return {
                "ok": True,
                "account": {
                    "id": acc.id,
                    "profile_id": acc.profile_id,
                    "cdp_port": acc.cdp_port,
                    "enabled": acc.enabled,
                    "note": acc.note,
                    "proxy": proxy_label(acc.proxy),
                    "has_proxy": bool(acc.proxy),
                },
            }
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.delete("/api/pool/accounts/{aid}")
    def api_pool_delete_account(aid: str, delete_vault: bool = False):
        try:
            return pool.remove_account(aid, delete_vault=delete_vault)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/api/pool/accounts/{aid}/detail")
    def api_pool_account_detail(aid: str):
        try:
            return pool.account_detail(aid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/api/circuit/clear")
    def api_clear_circuit(account: Optional[str] = None):  # GET intentionally: idempotent reset, no secrets
        if account:
            try:
                pool.reset_account(account)
            except KeyError as e:
                raise HTTPException(status_code=404, detail=str(e))
            return {"ok": True, "accounts": [account]}
        for a in pool.accounts:
            pool.reset_account(a.id)
        return {"ok": True, "accounts": [a.id for a in pool.accounts]}

    return router
