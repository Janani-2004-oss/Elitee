"""
All FastAPI route handlers.

Endpoints
---------
GET  /health          – liveness probe
GET  /checkout        – simulated order with dependency failures
GET  /simulate-load   – burst traffic generator
POST /emit-alert      – manual alert payload webhook forwarder
"""
import asyncio
import random
import time
from typing import Any

import httpx
from faker import Faker
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import User, RequestLog, get_db
from app.simulators import simulate_payment, simulate_inventory, simulate_external_api
from app import logger as log

router = APIRouter()
fake = Faker()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _pick_random_user(db: AsyncSession) -> User | None:
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return random.choice(users) if users else None


async def _persist_log(
    db: AsyncSession,
    *,
    status_code: int,
    latency_ms: float,
    payment_status: str,
    inventory_latency: float,
    external_api_latency: float,
    root_cause: str | None,
    error_type: str | None,
    user_id: int | None,
) -> None:
    entry = RequestLog(
        status_code=status_code,
        latency_ms=latency_ms,
        payment_status=payment_status,
        inventory_latency=inventory_latency,
        external_api_latency=external_api_latency,
        root_cause=root_cause,
        error_type=error_type,
        user_id=user_id,
    )
    db.add(entry)
    await db.commit()


def _decide_outcome(
    payment: dict,
    inventory: dict,
    external: dict,
    force_error: str | None,
    force_slow: bool,
) -> tuple[int, str | None, str | None]:
    """
    Return (status_code, error_type, root_cause) based on simulation results
    and any query-param overrides.
    """
    # ── forced overrides ──────────────────────────────────────────────────
    if force_error == "500":
        return 500, "internal_error", "unknown"
    if force_error == "502":
        return 502, "payment_failure", "payment"

    # ── dependency-driven outcomes ────────────────────────────────────────
    if payment["status"] == "timeout":
        return 504, "timeout", "payment"
    if payment["status"] == "failure":
        return 502, "payment_failure", "payment"
    if inventory["status"] == "failure":
        return 500, "inventory_error", "inventory"
    if external["status"] == "spike" and external["latency_ms"] > 8000:
        return 504, "timeout", "external_api"

    # ── probabilistic outcomes (matching the spec distribution) ──────────
    roll = random.random()
    if roll < 0.60:
        return 200, None, None
    if roll < 0.75:   # 15 %
        return 500, "internal_error", "unknown"
    if roll < 0.85:   # 10 %
        return 502, "payment_failure", "payment"
    if roll < 0.95:   # 10 %
        return 400, "invalid_request", None
    # 5 % – timeout
    return 504, "timeout", "external_api"


# ─────────────────────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["ops"])
async def health():
    """Kubernetes / Cloud Run liveness probe."""
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /checkout
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/checkout", tags=["order"])
async def checkout(
    force_error: str | None = Query(
        default=None,
        description="Force a specific HTTP error: 500 | 502",
    ),
    force_slow: bool = Query(
        default=False,
        description="Inject an artificial 8-second delay",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Simulates a full order checkout with three internal dependencies:
    payment service, inventory service, and an external API.

    Response distribution (random, without overrides):
      60% → 200   success
      15% → 500   internal error
      10% → 502   payment failure
      10% → 400   invalid request
       5% → 504   timeout (>8 s)
    """
    request_start = time.monotonic()

    # ── pick a synthetic user ─────────────────────────────────────────────
    user = await _pick_random_user(db)
    user_id = user.id if user else None
    email = user.email if user else fake.email()

    # ── forced slow path ──────────────────────────────────────────────────
    if force_slow:
        await asyncio.sleep(8.5)

    # ── run dependencies concurrently ─────────────────────────────────────
    payment_result, inventory_result, external_result = await asyncio.gather(
        simulate_payment(),
        simulate_inventory(),
        simulate_external_api(),
    )

    # ── decide final status ───────────────────────────────────────────────
    status_code, error_type, root_cause = _decide_outcome(
        payment_result, inventory_result, external_result,
        force_error, force_slow,
    )

    total_latency_ms = (time.monotonic() - request_start) * 1000

    # ── structured log ────────────────────────────────────────────────────
    log.emit_checkout(
        status_code=status_code,
        latency_ms=total_latency_ms,
        payment_status=payment_result["status"],
        inventory_latency=inventory_result["latency_ms"],
        external_api_latency=external_result["latency_ms"],
        error_type=error_type,
        root_cause=root_cause,
        user_id=user_id,
        email=email,
    )

    # ── persist to DB ─────────────────────────────────────────────────────
    await _persist_log(
        db,
        status_code=status_code,
        latency_ms=total_latency_ms,
        payment_status=payment_result["status"],
        inventory_latency=inventory_result["latency_ms"],
        external_api_latency=external_result["latency_ms"],
        root_cause=root_cause,
        error_type=error_type,
        user_id=user_id,
    )

    # ── build response body ───────────────────────────────────────────────
    body: dict[str, Any] = {
        "status_code": status_code,
        "latency_ms": round(total_latency_ms, 2),
        "user_id": user_id,
        "email": email,
        "dependencies": {
            "payment": {
                "status": payment_result["status"],
                "latency_ms": round(payment_result["latency_ms"], 2),
            },
            "inventory": {
                "status": inventory_result["status"],
                "latency_ms": round(inventory_result["latency_ms"], 2),
            },
            "external_api": {
                "status": external_result["status"],
                "latency_ms": round(external_result["latency_ms"], 2),
            },
        },
    }

    if error_type:
        body["error_type"] = error_type
        body["root_cause"] = root_cause

    if status_code >= 400:
        _ERROR_MESSAGES = {
            400: "Invalid order request",
            500: "Internal server error during checkout",
            502: "Payment gateway failure",
            504: "Upstream service timeout",
        }
        body["detail"] = _ERROR_MESSAGES.get(status_code, "Unknown error")

    return JSONResponse(content=body, status_code=status_code)


# ─────────────────────────────────────────────────────────────────────────────
# GET /simulate-load
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/simulate-load", tags=["load"])
async def simulate_load(
    requests: int = Query(
        default=None,
        description="Number of /checkout calls to fire (default: from config)",
    ),
):
    """
    Fires N concurrent /checkout requests against itself to generate
    burst traffic.  Uses httpx with an async client.
    """
    n = requests or settings.simulate_load_requests
    base_url = f"http://localhost:{settings.port}"

    log.emit({"event": "simulate_load_start", "n": n})

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        tasks = [client.get("/checkout") for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    status_counts: dict[int, int] = {}
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
        else:
            status_counts[r.status_code] = status_counts.get(r.status_code, 0) + 1

    summary = {
        "total_requests": n,
        "status_distribution": status_counts,
        "exceptions": errors,
    }
    log.emit({"event": "simulate_load_complete", **summary})
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# POST /emit-alert
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/emit-alert", tags=["alerting"])
async def emit_alert(payload: dict[str, Any]):
    """
    Accepts an arbitrary JSON payload and:
    1. Logs it as a structured alert event.
    2. Optionally forwards it to ALERT_WEBHOOK_URL (if configured).

    Useful for manual testing of alerting pipelines.
    """
    log.emit_alert(payload)

    forwarded = False
    if settings.alert_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    settings.alert_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            forwarded = True
            log.emit(
                {
                    "event": "alert_forwarded",
                    "webhook_url": settings.alert_webhook_url,
                    "response_status": resp.status_code,
                }
            )
        except Exception as exc:
            log.emit(
                {
                    "event": "alert_forward_failed",
                    "webhook_url": settings.alert_webhook_url,
                    "error": str(exc),
                }
            )

    return {
        "received": True,
        "forwarded_to_webhook": forwarded,
        "payload": payload,
    }
