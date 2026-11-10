import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.contexto import ip_actual, user_agent_actual
from app.routers import auditoria, auth, cartas_porte, catalogos, cotizaciones, facturas, insumos, reportes, usuarios

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Gestión Agro",
    description="Facturas de proveedores, cartas de porte y reportes de la empresa.",
    version="0.1.0",
    # Detrás de nginx la API vive en /api: así /api/docs encuentra /api/openapi.json.
    root_path="/api",
    docs_url="/docs" if settings.docs_publicas else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_publicas else None,
)

@app.middleware("http")
async def contexto_del_pedido(request: Request, call_next):
    """Deja la IP (que pone nginx en X-Real-IP) y el navegador a mano para la auditoría y las sesiones."""
    ip_actual.set(request.headers.get("x-real-ip") or (request.client.host if request.client else None))
    user_agent_actual.set(request.headers.get("user-agent"))
    return await call_next(request)


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
    return {"ok": True}
