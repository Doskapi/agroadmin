import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, cartas_porte, catalogos, facturas, reportes, usuarios

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Gestión Agro",
    description="Facturas de proveedores, cartas de porte y reportes de la empresa.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3001"],  # frontend futuro
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, usuarios, catalogos, facturas, cartas_porte, reportes):
    app.include_router(r.router)


@app.get("/salud", tags=["sistema"])
def salud():
    return {"ok": True}
