"""
Dependency simulators for payment, inventory, and external API.
Each returns a dict describing what happened (status, latency, error).
"""
import asyncio
import random
import time

from app.config import settings


# ---------------------------------------------------------------------------
# Payment Service
# ---------------------------------------------------------------------------

async def simulate_payment() -> dict:
    """
    Simulates an upstream payment gateway call.

    Returns:
        {
            "status": "success" | "failure" | "timeout",
            "latency_ms": float,
            "error_type": str | None,
            "root_cause": str | None,
        }
    """
    start = time.monotonic()
    roll = random.random()

    if roll < settings.payment_timeout_rate:
        # Timeout path – sleep long enough to look real
        await asyncio.sleep(random.uniform(6.0, 9.0))
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "status": "timeout",
            "latency_ms": latency_ms,
            "error_type": "timeout",
            "root_cause": "payment",
        }

    if roll < settings.payment_timeout_rate + settings.payment_failure_rate:
        await asyncio.sleep(random.uniform(0.05, 0.3))
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "status": "failure",
            "latency_ms": latency_ms,
            "error_type": "payment_failure",
            "root_cause": "payment",
        }

    # Happy path
    await asyncio.sleep(random.uniform(0.05, 0.4))
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "status": "success",
        "latency_ms": latency_ms,
        "error_type": None,
        "root_cause": None,
    }


# ---------------------------------------------------------------------------
# Inventory Service
# ---------------------------------------------------------------------------

async def simulate_inventory() -> dict:
    """
    Simulates a slow inventory / warehouse service with a random delay 0-4 s.

    Returns:
        {
            "status": "success" | "failure",
            "latency_ms": float,
            "error_type": str | None,
            "root_cause": str | None,
        }
    """
    start = time.monotonic()
    delay = random.uniform(0, settings.inventory_max_delay)
    await asyncio.sleep(delay)

    # 5% chance of inventory error
    if random.random() < 0.05:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "status": "failure",
            "latency_ms": latency_ms,
            "error_type": "inventory_error",
            "root_cause": "inventory",
        }

    latency_ms = (time.monotonic() - start) * 1000
    return {
        "status": "success",
        "latency_ms": latency_ms,
        "error_type": None,
        "root_cause": None,
    }


# ---------------------------------------------------------------------------
# External API
# ---------------------------------------------------------------------------

async def simulate_external_api() -> dict:
    """
    Simulates a 3rd-party API with occasional latency spikes.

    Returns:
        {
            "status": "success" | "spike",
            "latency_ms": float,
            "error_type": str | None,
            "root_cause": str | None,
        }
    """
    start = time.monotonic()

    if random.random() < settings.external_api_spike_prob:
        # Latency spike
        await asyncio.sleep(
            settings.external_api_spike_latency + random.uniform(0, 2.0)
        )
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "status": "spike",
            "latency_ms": latency_ms,
            "error_type": "latency_spike",
            "root_cause": "external_api",
        }

    await asyncio.sleep(random.uniform(0.02, 0.2))
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "status": "success",
        "latency_ms": latency_ms,
        "error_type": None,
        "root_cause": None,
    }
