# Roda NO PICO: testa Wi-Fi, HTTPS (r.raw.read) e o atualiza.tentar() contra um servidor no PC.
# Uso: python3 sim/teste_wifi.py <ip do PC>   (gera e roda isto com SERVIDOR preenchido)
import gc
import os
import time

import config
import network
import requests

import atualiza

SERVIDOR = "__SERVIDOR__"  # trocado pelo teste_wifi.py, ex.: http://192.168.100.6:8765
CENARIO = "__CENARIO__"


def wifi():
    t0 = time.ticks_ms()
    w = atualiza._conectar()
    if not w.isconnected():
        print("WIFI: nao conectou em %d s (status %d). Rede 2,4 GHz? senha?" % (config.WIFI_TIMEOUT_S, w.status()))
        w.active(False)
        raise SystemExit
    print("WIFI: conectou em %d ms, ip %s, rssi %d dBm" % (
        time.ticks_diff(time.ticks_ms(), t0), w.ifconfig()[0], w.status("rssi")))
    return w


def https():
    url = "https://raw.githubusercontent.com/murkiriel/pardal/main/README.md"
    t0 = time.ticks_ms()
    r = requests.get(url, headers={"User-Agent": "radar-pico"})
    print("HTTPS: status %d em %d ms, Content-Length %s" % (
        r.status_code, time.ticks_diff(time.ticks_ms(), t0), r.headers.get("Content-Length")))
    n, t0 = 0, time.ticks_ms()
    while True:
        p = r.raw.read(1024)
        if not p:
            break
        n += len(p)
    r.close()
    print("HTTPS: r.raw.read() leu %d bytes em %d ms" % (n, time.ticks_diff(time.ticks_ms(), t0)))

    # github.com/.../raw/... responde 302 para raw.githubusercontent.com
    url = "https://github.com/murkiriel/pardal/raw/main/README.md"
    try:
        r = requests.get(url, headers={"User-Agent": "radar-pico"})
        print("REDIRECT: requests.get direto -> status %d, Location %s" % (
            r.status_code, r.headers.get("Location") or r.headers.get("location")))
        r.close()
    except Exception as e:
        print("REDIRECT: requests.get direto levantou %r" % e)
    try:
        r = atualiza._get(url)
        n = len(r.content)
        print("REDIRECT: atualiza._get -> status %d, %d bytes" % (r.status_code, n))
        r.close()
    except Exception as e:
        print("REDIRECT: atualiza._get levantou %r" % e)


def estado():
    s = os.statvfs("/")
    arqs = [a for a in os.listdir() if a.startswith("radares")]
    print("FLASH: livre %d KB, arquivos %s, versao local %r" % (
        s[0] * s[3] // 1024, ["%s=%d" % (a, os.stat(a)[6]) for a in arqs], atualiza._ler(atualiza.ARQ_VERSAO)))


w = wifi()
if CENARIO == "https":
    https()
    w.disconnect()
    w.active(False)
else:
    w.disconnect()
    w.active(False)
    config.URL_BASE = SERVIDOR + "/radares.bin"
    config.URL_VERSAO = config.URL_BASE + ".versao"
    estado()
    gc.collect()
    t0 = time.ticks_ms()
    res = atualiza.tentar(lambda m: print("ATUALIZA: " + m))
    print("ATUALIZA: tentar() = %s em %d ms, wifi ativo depois: %s" % (
        res, time.ticks_diff(time.ticks_ms(), t0), network.WLAN(network.STA_IF).active()))
    estado()
print("fim")
