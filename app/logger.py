"""
Structured JSON logger.

Every checkout request emits one JSON line to stdout.
Cloud Run / GCP Logging / Datadog all pick this up automatically.
"""
import json
import logging
import sys
import datetime
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


def emit(record: dict[str, Any]) -> None:
    """
    Emit one structured JSON log line to stdout.

    Automatically injects:
      - timestamp (ISO-8601 UTC)
      - service name
    """
    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "service": settings.service_name,
        **record,
    }
    # Use print so the line goes straight to stdout with no extra formatting
    print(json.dumps(payload), flush=True)


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
    """Convenience wrapper for /checkout structured logs."""
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


def emit_alert(payload: dict[str, Any]) -> None:
    """Log a manual alert payload emission."""
    emit({"event": "alert_emitted", **payload})
