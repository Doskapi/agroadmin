import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, cartas_porte, catalogos, cotizaciones, facturas, insumos, reportes, usuarios

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

# En producción el frontend se sirve desde el mismo origen (nginx), así que no hace falta CORS.
if not settings.es_produccion:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

for r in (auth, usuarios, catalogos, insumos, cotizaciones, facturas, cartas_porte, reportes):
    app.include_router(r.router)


@app.get("/salud", tags=["sistema"])
def salud():
    return {"ok": True}
