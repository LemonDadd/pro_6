from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_workers: int = 1

    database_url: str = "sqlite:///./md2pdf.db"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    s3_endpoint_url: Optional[str] = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "md2pdf"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    pdf_ttl_days: int = 7

    sync_max_size_kb: int = 200
    sync_timeout_seconds: int = 30
    max_concurrent_jobs: int = 3
    daily_rate_limit: int = 100

    batch_max_files: int = 100
    batch_max_payload_kb: int = 10240

    allowed_css_domains: str = "localhost,cdn.jsdelivr.net,cdnjs.cloudflare.com"

    mermaid_renderer: str = "kroki"
    kroki_url: str = "http://localhost:8008"

    api_keys: str = "test-key-123"

    @property
    def allowed_css_domain_list(self) -> List[str]:
        return [d.strip() for d in self.allowed_css_domains.split(",") if d.strip()]

    @property
    def api_key_list(self) -> List[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
