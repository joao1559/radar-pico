"""requests falso (só para o import funcionar). Com Wi-Fi ligado no fake, troque `get` no teste."""


def get(url, headers=None, **kw):
    raise OSError("requests falso: sem rede no simulador")
