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
    # Sesiones: se cierran tras este tiempo sin uso, y como máximo duran sesion_maxima_horas.
    access_token_minutes: int = 480
    sesion_maxima_horas: int = 7 * 24
    # Cookie de sesión solo por HTTPS. "auto": según el protocolo con el que llegó el pedido.
    cookie_segura: Literal["auto", "si", "no"] = "auto"

    # Verificación en dos pasos obligatoria para quienes tengan alguno de estos permisos (separados por coma).
    exigir_2fa: str = "usuarios:admin,facturas:confirmar"

    # Correo saliente (recuperación de contraseña y avisos). Sin SMTP_HOST no se envían correos.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_usuario: str | None = None
    smtp_password: str | None = None
    smtp_remitente: str = "Gestión Agro <no-responder@localhost>"
    smtp_tls: bool = True
    # URL con la que los usuarios abren la app (para los links de los correos)
    url_publica: str = "http://localhost:8080"

    # Usuario de solo lectura para Metabase u otras herramientas de BI (se crea si hay contraseña)
    lector_db_password: str | None = None

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

    # Logs: "texto" (legible) o "json" (para juntarlos en un sistema de logs)
    log_formato: Literal["texto", "json"] = "texto"
    log_nivel: str = "INFO"
    # Errores a Sentry (opcional)
    sentry_dsn: str | None = None

    # El worker trae solo las cotizaciones del BCRA nuevas (si alguna vez se cargaron)
    cotizaciones_automaticas: bool = True

    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    # Esfuerzo de razonamiento: low | medium | high. Para leer facturas suele alcanzar con medium.
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "produccion"

    @property
    def permisos_con_2fa(self) -> set[str]:
        return {p.strip() for p in self.exigir_2fa.split(",") if p.strip()}

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
