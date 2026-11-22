from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Model ids are never hardcoded in application code."""

    model_config = SettingsConfigDict(env_prefix="CLAIMS_", env_file=".env", extra="ignore")

    aws_profile: str = "personal"
    aws_region: str = "eu-north-1"
    model_provider: str = "bedrock"
    # Cheapest capable default in eu-north-1; override via CLAIMS_MODEL_ID after eval.
    model_id: str = "eu.amazon.nova-micro-v1:0"
    data_dir: str = "data"
    approval_hmac_secret_env: str = "CLAIMS_APPROVAL_HMAC_SECRET"


settings = Settings()
