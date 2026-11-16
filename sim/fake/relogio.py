"""Relógio virtual: substitui time.ticks_ms/sleep_ms/sleep do MicroPython no CPython.
Dormir só avança o relógio, então um trajeto de minutos roda em segundos."""
import time as _time

PERIODO = 1 << 30  # igual ao rp2: ticks_ms dá a volta em 2^30 ms
agora_ms = 0
limite_ms = None   # trava de segurança: passou disso, encerra (loops infinitos sem UART)
_orig = {}


class FimDoTrajeto(BaseException):
    """Encerra o loop infinito do main.py (BaseException escapa de `except Exception`)."""


def avancar(ms):
    global agora_ms
    agora_ms += int(ms)
    if limite_ms is not None and agora_ms > limite_ms:
        raise FimDoTrajeto()


def ticks_ms():
    return agora_ms & (PERIODO - 1)


def ticks_add(t, delta):
    return (t + delta) & (PERIODO - 1)


def ticks_diff(a, b):
    meio = PERIODO // 2
    return ((a - b + meio) & (PERIODO - 1)) - meio


def sleep_ms(ms):
    avancar(ms)


def sleep(s):
    avancar(s * 1000)


def instalar(inicio_ms=0):
    global agora_ms
    agora_ms = inicio_ms
    for nome, f in (("ticks_ms", ticks_ms), ("ticks_add", ticks_add), ("ticks_diff", ticks_diff),
                    ("sleep_ms", sleep_ms), ("sleep", sleep)):
        if nome not in _orig:
            _orig[nome] = getattr(_time, nome, None)
        setattr(_time, nome, f)


def desinstalar():
    for nome, f in _orig.items():
        if f is None:
            delattr(_time, nome)
        else:
            setattr(_time, nome, f)
    _orig.clear()
