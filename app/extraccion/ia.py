"""Extracción de datos de facturas con Claude (PDF o imagen -> JSON validado)."""

import base64
import logging
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel, Field

from app.config import settings

log = logging.getLogger(__name__)

TIPOS_IMAGEN = {"image/jpeg", "image/png", "image/gif", "image/webp"}

PROMPT = """Sos un asistente administrativo de una empresa agropecuaria argentina.
Extraé los datos de este comprobante (factura, nota de crédito/débito o ticket) recibido de un proveedor.

- Los montos van como números con punto decimal (1.234,56 en el papel -> 1234.56).
- Fechas en formato AAAA-MM-DD.
- CUIT solo dígitos, sin guiones.
- tipo_comprobante es el código ARCA: 1=Factura A, 2=ND A, 3=NC A, 6=Factura B, 7=ND B, 8=NC B,
  11=Factura C, 12=ND C, 13=NC C, 51=Factura M. Si no se puede determinar, dejalo vacío.
- Si un dato no figura o no es legible, dejalo vacío: no lo inventes.
- categoria_sugerida: una de semillas, agroquimicos, fertilizantes, combustible, fletes, servicios,
  maquinaria, repuestos, honorarios, arrendamiento, otros.
"""


class ItemExtraido(BaseModel):
    descripcion: str
    cantidad: float | None = None
    unidad: str | None = None
    precio_unitario: float | None = None
    alicuota_iva: float | None = None
    subtotal: float | None = None


class FacturaExtraida(BaseModel):
    cuit_emisor: str | None = None
    razon_social_emisor: str | None = None
    condicion_iva_emisor: str | None = None
    tipo_comprobante: int | None = None
    letra: str | None = Field(default=None, description="A, B, C o M")
    punto_venta: int | None = None
    numero: int | None = None
    fecha_emision: str | None = None
    fecha_vencimiento: str | None = None
    moneda: str | None = Field(default=None, description="PES, DOL u otro código ARCA")
    cotizacion: float | None = None
    neto_gravado: float | None = None
    no_gravado: float | None = None
    iva: float | None = None
    percepciones: float | None = None
    total: float | None = None
    cae: str | None = None
    cae_vencimiento: str | None = None
    categoria_sugerida: str | None = None
    items: list[ItemExtraido] = []


class ErrorExtraccionIA(Exception):
    def __init__(self, mensaje: str, reintentable: bool = False):
        super().__init__(mensaje)
        # Errores pasajeros (límite de uso, sin conexión, servicio caído): conviene reintentar más tarde
        self.reintentable = reintentable


def disponible() -> bool:
    return bool(settings.anthropic_api_key)


# Modelos sin fallback del lado del servidor (la API rechaza el parámetro `fallbacks`)
SIN_FALLBACK = ("claude-haiku",)


@dataclass
class Uso:
    modelo: str
    tokens_entrada: int
    tokens_salida: int


def extraer(data: bytes, content_type: str) -> FacturaExtraida:
    return extraer_con_uso(data, content_type)[0]


def extraer_con_uso(data: bytes, content_type: str, modelo: str | None = None,
                    effort: str | None = None) -> tuple[FacturaExtraida, Uso]:
    """Extrae los datos del comprobante. `modelo`/`effort` permiten comparar alternativas (ver evaluar.py)."""
    if content_type == "application/pdf":
        bloque = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                  "data": base64.standard_b64encode(data).decode()}}
    elif content_type in TIPOS_IMAGEN:
        bloque = {"type": "image", "source": {"type": "base64", "media_type": content_type,
                                               "data": base64.standard_b64encode(data).decode()}}
    else:
        raise ErrorExtraccionIA(f"Tipo de archivo no soportado para IA: {content_type}")

    modelo = modelo or settings.claude_model
    extra = {}
    if not modelo.startswith(SIN_FALLBACK):
        # Si un clasificador de seguridad rechaza el pedido, la API lo reintenta en otro modelo.
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.beta.messages.parse(
            model=modelo,
            max_tokens=16000,
            output_config={"effort": effort or settings.claude_effort},
            messages=[{"role": "user", "content": [bloque, {"type": "text", "text": PROMPT}]}],
            output_format=FacturaExtraida,
            **extra,
        )
    except anthropic.RateLimitError as e:
        raise ErrorExtraccionIA("Límite de uso de la API de Claude alcanzado, reintentar más tarde", True) from e
    except anthropic.APIStatusError as e:
        log.error("Error de la API de Claude (%s): %s", e.status_code, e.message)
        raise ErrorExtraccionIA(f"Error de la API de Claude ({e.status_code}), reintentar más tarde",
                                e.status_code >= 500) from e
    except anthropic.APIConnectionError as e:
        raise ErrorExtraccionIA("No se pudo conectar con la API de Claude", True) from e

    if response.stop_reason == "refusal":
        raise ErrorExtraccionIA("El modelo rechazó procesar el documento")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise ErrorExtraccionIA("La respuesta del modelo quedó incompleta")
    uso = Uso(response.model, response.usage.input_tokens, response.usage.output_tokens)
    log.info("Extracción con %s: %s tokens de entrada, %s de salida", uso.modelo, uso.tokens_entrada,
             uso.tokens_salida)
    return response.parsed_output, uso
