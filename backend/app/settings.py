from urllib.parse import quote

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    conductor_url: str = ''
    conductor_host: str = 'localhost'
    conductor_metrics_url: str = ''
    control_plane_token: str = Field(min_length=32)
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-2.5-flash'
    enable_gemini: bool = False

    # Application-owned persistence. Separate database from Conductor's own schema.
    database_url: str = ''
    database_host: str = 'localhost'
    database_port: int = 5432
    database_name: str = 'orchestra'
    database_admin_name: str = 'postgres'
    database_user: str = 'conductor'
    database_password: str = ''
    postgres_password: str = ''

    # Single-owner login. Empty disables password login; the master token still works.
    owner_password: str = ''
    session_ttl_hours: int = 720
    login_attempts_per_minute: int = 8

    # Optional Conductor task domain. Workers poll WORKER_DOMAIN; executions are
    # started with "<TASK_DOMAIN>, NO_DOMAIN" so a missing fleet falls back safely.
    task_domain: str = ''

    # Monitoring collector (runs inside the API process).
    monitor_enabled: bool = True
    monitor_tick_seconds: float = 2.0
    monitor_concurrency: int = 4
    monitor_retention_days: int = 14
    monitor_retention_observations: int = 2000
    http_check_allow_private: bool = False
    http_check_max_redirects: int = 0

    # Encrypts connector credentials at rest. Derived from the control-plane token when unset.
    secret_key: str = ''

    @model_validator(mode="after")
    def resolve_urls(self):
        if not self.conductor_url:
            self.conductor_url = f"http://{self.conductor_host}:8080/api"
        if not self.conductor_metrics_url:
            self.conductor_metrics_url = self.conductor_url.removesuffix('/api') + '/actuator/prometheus'
        if not self.database_password:
            self.database_password = self.postgres_password
        if not self.database_url:
            self.database_url = (
                f"postgresql://{quote(self.database_user, safe='')}:"
                f"{quote(self.database_password, safe='')}@"
                f"{self.database_host}:{self.database_port}/{self.database_name}"
            )
        return self
