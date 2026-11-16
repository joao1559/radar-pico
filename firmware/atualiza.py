# Atualiza o radares.bin pelo Wi-Fi, se a rede configurada estiver ao alcance.
import os
import time

import network
import requests  # micropython-lib (vem no firmware do Pico W)

import config

ARQ = "radares.bin"
ARQ_VERSAO = "radares.versao"
TMP = "radares.tmp"


def _conectar():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(config.WIFI_SSID, config.WIFI_SENHA)
    fim = time.ticks_add(time.ticks_ms(), config.WIFI_TIMEOUT_S * 1000)
    while not wlan.isconnected() and time.ticks_diff(fim, time.ticks_ms()) > 0:
        time.sleep_ms(200)
    return wlan


def _get(url):
    # Segue redirecionamentos manualmente (raw.githubusercontent normalmente não redireciona).
    for _ in range(3):
        r = requests.get(url, headers={"User-Agent": "radar-pico"})
        if r.status_code in (301, 302, 303, 307, 308):
            url = r.headers.get("Location") or r.headers.get("location")
            r.close()
            continue
        return r
    raise OSError("redirecionamentos demais")


def _ler(caminho):
    try:
        with open(caminho) as f:
            return f.read().strip()
    except OSError:
        return ""


def _livre():
    s = os.statvfs("/")
    return s[0] * s[3]


def _valido(caminho):
    import struct
    with open(caminho, "rb") as f:
        magic, versao, _, n_cel, n_reg = struct.unpack("<4sHHII", f.read(16))
    tam = os.stat(caminho)[6]
    return magic == b"PRDL" and versao == 1 and tam == 16 + n_cel * 10 + n_reg * 16


def tentar(aviso=print):
    """Devolve True se baixou uma base nova."""
    wlan = _conectar()
    if not wlan.isconnected():
        wlan.active(False)
        return False
    try:
        r = _get(config.URL_VERSAO)
        nova = r.text.strip() if r.status_code == 200 else ""
        r.close()
        if not nova or nova == _ler(ARQ_VERSAO):
            aviso("base em dia")
            return False

        r = _get(config.URL_BASE)
        if r.status_code != 200:
            r.close()
            aviso("erro HTTP %d" % r.status_code)
            return False
        tam = int(r.headers.get("Content-Length", 0) or 0)
        # Flash pequena: se não couber a base velha + a nova, apaga a velha antes.
        if tam and _livre() < tam + 8192 and ARQ in os.listdir():
            os.remove(ARQ)
        aviso("baixando %d KB" % (tam // 1024))
        with open(TMP, "wb") as f:
            while True:
                pedaco = r.raw.read(1024)
                if not pedaco:
                    break
                f.write(pedaco)
        r.close()

        if not _valido(TMP):
            os.remove(TMP)
            aviso("arquivo inválido")
            return False
        if ARQ in os.listdir():
            os.remove(ARQ)
        os.rename(TMP, ARQ)
        with open(ARQ_VERSAO, "w") as f:
            f.write(nova)
        aviso("base atualizada")
        return True
    except Exception as e:  # sem rede boa, segue com a base que já tem
        aviso("falha: %s" % e)
        return False
    finally:
        wlan.disconnect()
        wlan.active(False)  # desliga o rádio: economiza energia e evita interferência no GPS
