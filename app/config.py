"""
Configuration management using environment variables.
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service metadata
    service_name: str = "order-service"
    port: int = 8080

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@elitee-db-1:5432/orderdb",
    )

    # Simulation knobs
    payment_failure_rate: float = 0.20   # 20%
    payment_timeout_rate: float = 0.10   # 10%
    inventory_max_delay: float = 4.0     # seconds
    external_api_spike_prob: float = 0.15
    external_api_spike_latency: float = 3.0  # seconds

    # Load simulation
    simulate_load_requests: int = 20

    # Webhook / alert target (optional)
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
