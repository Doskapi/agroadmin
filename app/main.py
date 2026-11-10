import logging
import time
import uuid
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.config import settings
from app.contexto import ip_actual, nuevo_pedido, user_agent_actual
from app.db import SessionLocal
from app.logs import configurar_logs, request_id
from app.models import TareaProgramada
from app.routers import auditoria, auth, cartas_porte, catalogos, cotizaciones, facturas, insumos, reportes, usuarios
from app.sesiones import ahora

configurar_logs()
log_pedidos = logging.getLogger("app.pedidos")

app = FastAPI(
    title="Gestión Agro",
    description="Facturas de proveedores, cartas de porte y reportes de la empresa.",
    version="0.1.0",
    # Detrás de nginx la API vive en /api ("Try it out" de la documentación apunta ahí)
    servers=[{"url": "/api"}],
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_publicas else None,
)

if settings.docs_publicas:
    @app.get("/docs", include_in_schema=False)
    def documentacion():
        return get_swagger_ui_html(openapi_url="/api/openapi.json", title="Gestión Agro - API")

@app.middleware("http")
async def contexto_del_pedido(request: Request, call_next):
    """Deja la IP (que pone nginx en X-Real-IP), el navegador y un id de pedido a mano para la auditoría,
    las sesiones y los logs, y registra cada pedido con su duración."""
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    ip_actual.set(ip)
    user_agent_actual.set(request.headers.get("user-agent"))
    pedido = nuevo_pedido()
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request_id.set(rid)
    inicio = time.perf_counter()
    estado = 500
    try:
        response = await call_next(request)
        estado = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        ms = round((time.perf_counter() - inicio) * 1000, 1)
        nivel = logging.WARNING if estado >= 500 else logging.INFO
        log_pedidos.log(nivel, "%s %s %s %sms", request.method, request.url.path, estado, ms,
                        extra={"metodo": request.method, "ruta": request.url.path, "estado": estado,
                               "duracion_ms": ms, "usuario_id": pedido.get("usuario_id"), "ip": ip})


# En producción el frontend se sirve desde el mismo origen (nginx), así que no hace falta CORS.
if not settings.es_produccion:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

for r in (auth, usuarios, auditoria, catalogos, insumos, cotizaciones, facturas, cartas_porte, reportes):
    app.include_router(r.router)


@app.get("/salud", tags=["sistema"])
def salud():
    """Estado del sistema: base de datos y worker (que late cada 30 segundos)."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            latido = db.scalar(select(TareaProgramada.ultima_ejecucion).where(TareaProgramada.nombre == "_latido"))
    except Exception:
        logging.getLogger(__name__).exception("La base de datos no responde")
        return JSONResponse({"ok": False, "base_de_datos": False}, status_code=503)
    worker = latido is not None and latido > ahora() - timedelta(minutes=2)
    return {"ok": True, "base_de_datos": True, "worker": worker, "ultimo_latido_worker": latido}
