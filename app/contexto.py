"""Datos del pedido HTTP en curso, accesibles desde cualquier parte (auditoría, sesiones)."""

from contextvars import ContextVar

ip_actual: ContextVar[str | None] = ContextVar("ip_actual", default=None)
user_agent_actual: ContextVar[str | None] = ContextVar("user_agent_actual", default=None)
