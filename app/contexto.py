"""Datos del pedido HTTP en curso, accesibles desde cualquier parte (auditoría, sesiones)."""

from contextvars import ContextVar

ip_actual: ContextVar[str | None] = ContextVar("ip_actual", default=None)
user_agent_actual: ContextVar[str | None] = ContextVar("user_agent_actual", default=None)
# Diccionario mutable por pedido: las dependencias síncronas de FastAPI corren en otro hilo con una copia del
# contexto, así que un ContextVar.set() ahí no llega al middleware; modificar el mismo dict sí.
datos_pedido: ContextVar[dict] = ContextVar("datos_pedido")


def nuevo_pedido() -> dict:
    d: dict = {}
    datos_pedido.set(d)
    return d


def set_usuario(usuario_id: int) -> None:
    try:
        datos_pedido.get()["usuario_id"] = usuario_id
    except LookupError:  # fuera de un pedido HTTP (worker, scripts)
        pass
