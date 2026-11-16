"""Testa a atualização pelo Wi-Fi no Pico real, servindo a base a partir do PC.

  python3 sim/teste_wifi.py https                     -> só Wi-Fi + HTTPS no GitHub
  python3 sim/teste_wifi.py <cenario> [--porta COM5]  -> nova | igual | corrompida | cortada | travada | restaura

O Pico usa WIFI_SSID/WIFI_SENHA do config.py que está NA PLACA. O PC precisa estar na mesma rede
(o Pico W só pega 2,4 GHz) e o firewall do Windows precisa deixar entrar na porta 8765.
"""
import hashlib
import http.server
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA_HTTP = 8765


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.0.1", 9))  # não manda nada; só escolhe a interface da rede local
        return s.getsockname()[0]
    finally:
        s.close()


def preparar(pasta, cenario):
    with open(os.path.join(AQUI, "radares.bin"), "rb") as f:
        dados = f.read()
    if cenario == "corrompida":
        dados = dados[: len(dados) // 2]  # download "cortado no meio"
    versao = hashlib.sha256(dados).hexdigest()
    if cenario in ("cortada", "travada"):
        versao = cenario + "-" + versao[:16]  # versão nova; o 1º download falha (ver servir)
    if cenario == "restaura":
        versao = "restaura-" + versao[:16]  # força versão diferente da que estiver na placa
    with open(os.path.join(pasta, "radares.bin"), "wb") as f:
        f.write(dados)
    with open(os.path.join(pasta, "radares.bin.versao"), "w") as f:
        f.write(versao + "\n")


def servir(pasta, cenario):
    downloads = []
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=pasta, **kw)

        def copyfile(self, origem, destino):
            if self.path.endswith(".bin") and cenario in ("cortada", "travada"):
                downloads.append(1)
                if len(downloads) == 1:  # só o 1º download falha: o Pico tem que se recuperar sozinho
                    destino.write(origem.read(150 * 1024))  # anuncia o tamanho todo...
                    if cenario == "travada":
                        time.sleep(40)  # ...e para de mandar sem fechar (Wi-Fi ruim)
                    self.close_connection = True  # ...ou derruba a conexão
                    return
            super().copyfile(origem, destino)

        def log_message(self, fmt, *a):
            print("  [PC] %s %s" % (self.client_address[0], fmt % a))

    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PORTA_HTTP), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    args = sys.argv[1:]
    porta = "COM5"
    if "--porta" in args:
        i = args.index("--porta")
        porta = args[i + 1]
        del args[i:i + 2]
    cenario = args[0] if args else "nova"
    with open(os.path.join(AQUI, "teste_wifi_pico.py"), encoding="utf-8") as f:
        src = f.read().replace("__CENARIO__", cenario)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
        srv = None
        if cenario != "https":
            preparar(pasta, cenario)
            srv = servir(pasta, cenario)
            src = src.replace("__SERVIDOR__", "http://%s:%d" % (ip_local(), PORTA_HTTP))
        script = os.path.join(pasta, "teste_pico.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(src)
        try:
            r = subprocess.run(["uvx", "mpremote", "connect", porta, "run", script], timeout=240)
        finally:
            if srv:
                srv.shutdown()
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
