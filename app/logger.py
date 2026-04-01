"""
Structured JSON logger with Datadog integration.

- Prints logs to stdout (Render picks this up)
- Sends logs directly to Datadog via HTTP API
"""

import json
import logging
import sys
import datetime
import os
import requests
from typing import Any

from app.config import settings


# ---------------------------------------------------------------------------
# Root logger – writes plain text for framework noise
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(levelname)s\t%(name)s\t%(message)s",
)

# Dedicated structlog-style logger (writes raw JSON)
_struct_logger = logging.getLogger("struct")


# ---------------------------------------------------------------------------
# Core emit function
# ---------------------------------------------------------------------------
def emit(record: dict[str, Any]) -> None:
    """
    Emit one structured JSON log line.

    - Sends to stdout (Render logs)
    - Sends to Datadog (if API key present)
    """
    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "service": settings.service_name,
        **record,
    }

    # ✅ 1. Print to stdout (for Render / local logs)
    print(json.dumps(payload), flush=True)

    # ✅ 2. Send to Datadog (non-blocking, safe)
    DATADOG_API_KEY = os.getenv("DATADOG_API_KEY")

    if DATADOG_API_KEY:
        try:
            requests.post(
                "https://http-intake.logs.us5.datadoghq.com/v1/input",
                headers={
                    "Content-Type": "application/json",
                    "DD-API-KEY": DATADOG_API_KEY,
                },
                json=payload,
                timeout=2,  # don't slow down app
            )
        except Exception:
            pass  # never break app due to logging


# ---------------------------------------------------------------------------
# Checkout log helper
# ---------------------------------------------------------------------------
def emit_checkout(
    *,
    status_code: int,
    latency_ms: float,
    payment_status: str,
    inventory_latency: float,
    external_api_latency: float,
    error_type: str | None,
    root_cause: str | None,
    user_id: int | None,
    email: str | None,
) -> None:
    """Structured log for checkout endpoint."""
    emit(
        {
            "event": "checkout_request",
            "status_code": status_code,
            "latency_ms": round(latency_ms, 2),
            "payment_status": payment_status,
            "inventory_latency": round(inventory_latency, 2),
            "external_api_latency": round(external_api_latency, 2),
            "error_type": error_type,
            "root_cause": root_cause,
            "user_id": user_id,
            "email": email,
        }
    )


# ---------------------------------------------------------------------------
# Alert log helper
# ---------------------------------------------------------------------------
def emit_alert(payload: dict[str, Any]) -> None:
    """Log alert events."""
    emit({"event": "alert_emitted", **payload})