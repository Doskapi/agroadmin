"""Bloqueo de intentos de login fallidos, en memoria (sirve para un solo proceso de la API).

Cuenta los fallos por email y por IP dentro de una ventana deslizante. Al superar el máximo,
el login responde 429 hasta que los fallos más viejos salgan de la ventana.
"""

import threading
import time
from collections import defaultdict, deque

from app.config import settings

_fallos: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _ventana() -> float:
    return settings.login_ventana_minutos * 60


def _limpiar(clave: str, ahora: float) -> deque[float]:
    d = _fallos[clave]
    while d and d[0] <= ahora - _ventana():
        d.popleft()
    return d


def _claves(email: str, ip: str) -> list[tuple[str, int]]:
    return [(f"email:{email}", settings.login_max_intentos_email), (f"ip:{ip}", settings.login_max_intentos_ip)]


def segundos_de_bloqueo(email: str, ip: str) -> int:
    """0 si puede intentar; si no, cuántos segundos faltan para que pueda."""
    ahora = time.monotonic()
    espera = 0.0
    with _lock:
        for clave, maximo in _claves(email, ip):
            d = _limpiar(clave, ahora)
            if len(d) >= maximo:
                espera = max(espera, d[len(d) - maximo] + _ventana() - ahora)
    return int(espera) + 1 if espera > 0 else 0


def registrar_fallo(email: str, ip: str) -> None:
    ahora = time.monotonic()
    with _lock:
        for clave, _ in _claves(email, ip):
            _limpiar(clave, ahora).append(ahora)


def registrar_exito(email: str) -> None:
    with _lock:
        _fallos.pop(f"email:{email}", None)


def reiniciar() -> None:
    with _lock:
        _fallos.clear()
