from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application and ClickHouse MCP settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    service_name: str = "tenders-agent"
    adk_app_name: str = "tenders_agent"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8001
    postgres_url: str = Field(default="")
    api_key_postgres_url: str = Field(default="")
    postgres_endpoint: str = Field(default="")
    postgres_user: str = Field(default="")
    postgres_password: str = Field(default="")

    clickhouse_mcp_command: str = "mcp-clickhouse"
    clickhouse_host: str = Field(default="localhost")
    clickhouse_port: str = "8123"
    clickhouse_user: str = Field(default="default")
    clickhouse_password: str = Field(default="")
    clickhouse_database: str = "default"
    clickhouse_secure: str = "false"
    clickhouse_verify: str = "false"
    clickhouse_connect_timeout: str = "30"
    clickhouse_send_receive_timeout: str = "30"

    gemini_model: str = "gemini-flash-latest"
    """Model id passed to ADK Gemini (maps to tiered quotas, e.g. Gemini 3 Flash)."""

    parallel_comprehensive_diagnostics: bool = True
    """If True, run the four-way comprehensive review concurrently (faster TPM spike)."""

    gemini_http_retry_attempts: int = 8
    gemini_http_retry_initial_delay_sec: float = 25.0
    gemini_http_retry_max_delay_sec: float = 120.0

    @field_validator("parallel_comprehensive_diagnostics", mode="before")
    @classmethod
    def _coerce_bool(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return value

    def clickhouse_mcp_env(self) -> dict[str, str]:
        return {
            "CLICKHOUSE_HOST": self.clickhouse_host,
            "CLICKHOUSE_PORT": self.clickhouse_port,
            "CLICKHOUSE_USER": self.clickhouse_user,
            "CLICKHOUSE_PASSWORD": self.clickhouse_password,
            "CLICKHOUSE_DATABASE": self.clickhouse_database,
            "CLICKHOUSE_SECURE": self.clickhouse_secure,
            "CLICKHOUSE_VERIFY": self.clickhouse_verify,
            "CLICKHOUSE_CONNECT_TIMEOUT": self.clickhouse_connect_timeout,
            "CLICKHOUSE_SEND_RECEIVE_TIMEOUT": self.clickhouse_send_receive_timeout,
        }

    def api_key_postgres_connect_kwargs(self) -> dict[str, str]:
        """Return asyncpg connection kwargs for the backend api_keys database."""
        dsn = self.api_key_postgres_url or self.postgres_endpoint or self.postgres_url
        if not dsn:
            return {}

        kwargs = {"dsn": dsn.replace("postgresql+asyncpg://", "postgresql://", 1)}
        if self.postgres_endpoint:
            if self.postgres_user:
                kwargs["user"] = self.postgres_user
            if self.postgres_password:
                kwargs["password"] = self.postgres_password

        return kwargs


settings = Settings()
