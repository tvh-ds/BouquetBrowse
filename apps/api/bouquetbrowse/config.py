from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_mode: str = "demo"
    database_url: str = f"sqlite:///{ROOT / '.data' / 'bouquetbrowse.db'}"
    demo_secret: str = "localhost-demo-only-not-for-production"
    internal_api_token: str = "localhost-proxy-demo-token"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_storage_bucket: str = "bouquet-media"
    openai_api_key: str = ""
    extraction_model: str = "gpt-6-luna"
    escalation_model: str = "gpt-6.1-sol"
    embedding_model: str = "text-embedding-3-small"
    monthly_model_budget_usd: float = 50
    per_request_reservation_usd: float = 0.10
    threads_access_token: str = ""
    threads_search_approved: bool = False
    threads_api_base: str = "https://graph.threads.net/v1.0"
    instagram_access_token: str = ""
    instagram_user_id: str = ""
    instagram_graph_version: str = ""
    instagram_discovery_approved: bool = False
    extraction_provider: str = "rules"
    image_embedding_provider: str = "disabled"
    siglip_revision: str = ""
    media_dir: Path = ROOT / ".data" / "media"
    public_origin: str = "http://localhost:3000"

    @model_validator(mode="after")
    def validate_environment(self):
        if self.app_mode not in {"demo", "pilot"}:
            raise ValueError("APP_MODE must be demo or pilot")
        if self.app_mode == "pilot":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Pilot requires PostgreSQL")
            if not self.supabase_url.startswith("https://") or not self.supabase_publishable_key:
                raise ValueError("Pilot requires Supabase Auth configuration")
            if not self.supabase_secret_key:
                raise ValueError("Pilot requires a server-only Supabase Storage key")
            if len(self.internal_api_token) < 32 or self.internal_api_token == "localhost-proxy-demo-token":
                raise ValueError("Pilot requires a unique INTERNAL_API_TOKEN of at least 32 characters")
            if not self.public_origin.startswith("https://"):
                raise ValueError("Pilot requires an HTTPS PUBLIC_ORIGIN")
        if self.extraction_provider not in {"rules", "openai"}:
            raise ValueError("Unknown extraction provider")
        if self.image_embedding_provider not in {"disabled", "siglip"}:
            raise ValueError("Unknown image embedding provider")
        if self.monthly_model_budget_usd <= 0 or self.per_request_reservation_usd <= 0:
            raise ValueError("Model spending limits must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
