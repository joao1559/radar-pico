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


TIMEOUT_S = 15   # por operação de rede; sem isso uma conexão travada prende o boot para sempre
TENTATIVAS = 3   # downloads cortados: tenta de novo enquanto o Wi-Fi está ligado


def _get(url):
    # O requests do MicroPython 1.28 já segue redirecionamentos; isto é só uma garantia.
    for _ in range(3):
        r = requests.get(url, headers={"User-Agent": "radar-pico"}, timeout=TIMEOUT_S)
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
    try:
        with open(caminho, "rb") as f:
            magic, versao, _, n_cel, n_reg = struct.unpack("<4sHHII", f.read(16))
        tam = os.stat(caminho)[6]
    except (OSError, ValueError):  # arquivo vazio ou com menos de 16 bytes
        return False
    return magic == b"PRDL" and versao == 1 and tam == 16 + n_cel * 10 + n_reg * 16


def _apagar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


def _baixar(aviso):
    """Baixa config.URL_BASE para TMP. Devolve True se o arquivo chegou inteiro e válido."""
    r = _get(config.URL_BASE)
    try:
        if r.status_code != 200:
            aviso("erro HTTP %d" % r.status_code)
            return False
        tam = int(r.headers.get("Content-Length", 0) or 0)
        # Flash pequena: se não couber a base velha + a nova, apaga a velha antes.
        # A versão local vai junto, para o próximo boot saber que precisa baixar de novo.
        if tam and _livre() < tam + 8192 and ARQ in os.listdir():
            os.remove(ARQ)
            _apagar(ARQ_VERSAO)
        aviso("baixando %d KB" % (tam // 1024))
        n = 0
        with open(TMP, "wb") as f:
            while True:
                pedaco = r.raw.read(1024)
                if not pedaco:
                    break
                f.write(pedaco)
                n += len(pedaco)
    finally:
        r.close()
    if (tam and n != tam) or not _valido(TMP):
        _apagar(TMP)
        aviso("arquivo ruim (%d de %d KB)" % (n // 1024, tam // 1024))
        return False
    return True


def tentar(aviso=print):
    """Devolve True se baixou uma base nova."""
    wlan = _conectar()
    if not wlan.isconnected():
        wlan.active(False)
        return False
    try:
        _apagar(TMP)  # sobra de um download interrompido (ex.: desligou o carro no meio)
        r = _get(config.URL_VERSAO)
        nova = r.text.strip() if r.status_code == 200 else ""
        r.close()
        tem_base = ARQ in os.listdir()
        if not nova or (nova == _ler(ARQ_VERSAO) and tem_base):
            aviso("base em dia" if nova else "sem versao no servidor")
            return False

        for i in range(TENTATIVAS):
            try:
                if _baixar(aviso):
                    break
            except Exception as e:  # timeout ou conexão caiu no meio
                _apagar(TMP)
                aviso("falha: %s" % e)
            if i < TENTATIVAS - 1:
                aviso("tentando de novo (%d/%d)" % (i + 2, TENTATIVAS))
                time.sleep(2)
        else:
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
