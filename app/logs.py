"""Configuración de logs: texto legible o JSON (una línea por evento), con el id del pedido HTTP."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from app.config import settings

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class _ConRequestId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get() or "-"
        return True


class FormatoJSON(logging.Formatter):
    CAMPOS_EXTRA = ("metodo", "ruta", "estado", "duracion_ms", "usuario_id", "ip")

    def format(self, record: logging.LogRecord) -> str:
        datos = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for k in self.CAMPOS_EXTRA:
            if (v := getattr(record, k, None)) is not None:
                datos[k] = v
        if record.exc_info:
            datos["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False)


def configurar_logs() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ConRequestId())
    if settings.log_formato == "json":
        handler.setFormatter(FormatoJSON())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.handlers[:] = [handler]
    raiz.setLevel(settings.log_nivel.upper())
    # El access log de uvicorn se reemplaza por el nuestro (con usuario, duración e id de pedido)
    logging.getLogger("uvicorn.access").disabled = True

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.entorno, send_default_pii=False,
                        traces_sample_rate=0.0)
