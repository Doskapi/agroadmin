from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores de ejemplo que nunca se aceptan en producción.
CLAVES_DE_EJEMPLO = {
    "dev-inseguro-cambiar",
    "cambiar-por-una-clave-larga-y-aleatoria",
    "cambiar-esta-clave",
    "admin",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # En "produccion" (por defecto) la app no arranca con claves débiles o de ejemplo.
    entorno: Literal["produccion", "desarrollo"] = "produccion"

    database_url: str = "postgresql+psycopg://agro:agro@localhost:5432/agro"
    secret_key: str = "dev-inseguro-cambiar"
    access_token_minutes: int = 480

    admin_email: str = "admin@example.com"
    admin_password: str = "admin"

    storage_dir: Path = Path("data/archivos")
    max_upload_mb: int = 20
    max_paginas_pdf: int = 30

    # Bloqueo de login: tantos intentos fallidos en la ventana -> 429 hasta que pase la ventana.
    login_max_intentos_email: int = 5
    login_max_intentos_ip: int = 20
    login_ventana_minutos: int = 15

    # /docs y /openapi.json. Apagados en producción salvo que se pidan.
    docs_publicas: bool = False

    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"

    @model_validator(mode="after")
    def _exigir_secret_key(self):
        if self.es_produccion and (self.secret_key in CLAVES_DE_EJEMPLO or len(self.secret_key) < 32):
            raise ValueError(
                "SECRET_KEY falta, es de ejemplo o tiene menos de 32 caracteres. Generá una con:\n"
                "  python -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
                "(o poné ENTORNO=desarrollo para usar valores de prueba en tu máquina)"
            )
        return self


def password_debil(password: str) -> str | None:
    """Motivo por el que una contraseña no sirve, o None si está bien."""
    if len(password) < 10:
        return "debe tener al menos 10 caracteres"
    if password.lower() in CLAVES_DE_EJEMPLO:
        return "es un valor de ejemplo"
    return None


settings = Settings()
