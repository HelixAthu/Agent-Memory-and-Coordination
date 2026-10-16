"""Application settings loaded from environment variables and .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for Memory Fabric."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # FalkorDB Database
    falkordb_host: str = Field(default="localhost", alias="FALKORDB_HOST")
    falkordb_port: int = Field(default=6379, alias="FALKORDB_PORT")

    # Tenancy & API Auth
    tenants: str = Field(default="acme,globex", alias="TENANTS")
    tenant_keys: str = Field(default="acme:acme-demo-key,globex:globex-demo-key", alias="TENANT_KEYS")

    # Agent Runtime
    agent_mode: str = Field(default="mock", alias="AGENT_MODE")
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.8-flash", alias="GEMINI_MODEL")
    gemini_thinking_level: str = Field(default="medium", alias="GEMINI_THINKING_LEVEL")

    # Embeddings
    embed_provider: str = Field(default="mock", alias="EMBED_PROVIDER")
    embed_dim: int = Field(default=4096, alias="EMBED_DIM")
    embed_model: str = Field(default="gemini-embedding-001", alias="EMBED_MODEL")

    # Time & Concurrency
    clock_now: str = Field(default="", alias="CLOCK_NOW")
    max_inflight: int = Field(default=64, alias="MAX_INFLIGHT")

    def get_allowed_tenants(self) -> list[str]:
        """Return list of configured tenant identifiers."""
        return [t.strip() for t in self.tenants.split(",") if t.strip()]

    def get_tenant_api_keys(self) -> dict[str, str]:
        """Return mapping of tenant_id to expected API key."""
        keys: dict[str, str] = {}
        for entry in self.tenant_keys.split(","):
            if ":" in entry:
                tid, k = entry.strip().split(":", 1)
                keys[tid.strip()] = k.strip()
        return keys


settings: Settings = Settings()
