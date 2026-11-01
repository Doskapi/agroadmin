from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://agro:agro@localhost:5432/agro"
    secret_key: str = "dev-inseguro-cambiar"
    access_token_minutes: int = 480

    admin_email: str = "admin@example.com"
    admin_password: str = "admin"

    storage_dir: Path = Path("data/archivos")
    max_upload_mb: int = 20

    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"


settings = Settings()
