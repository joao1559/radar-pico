"""network falso. Por padrão a rede não aparece (cenário do carro); `conecta=True` simula garagem."""
import relogio

STA_IF, AP_IF = 0, 1
conecta = False
log = []


class WLAN:
    def __init__(self, iface=STA_IF):
        self._ativo = False
        self._conectado = False
        self._t_conecta = None

    def active(self, v=None):
        if v is None:
            return self._ativo
        self._ativo = bool(v)
        log.append(("active", self._ativo))
        if not v:
            self._conectado = False

    def connect(self, ssid, senha):
        if not self._ativo:
            raise OSError("WLAN inativa: chame active(True) antes")
        log.append(("connect", ssid))
        self._t_conecta = relogio.agora_ms + 2500

    def isconnected(self):
        if conecta and self._ativo and self._t_conecta is not None and relogio.agora_ms >= self._t_conecta:
            self._conectado = True
        return self._conectado

    def disconnect(self):
        log.append(("disconnect",))
        self._conectado = False

    def status(self, *a):
        return 3 if self._conectado else 0

    def ifconfig(self):
        return ("192.168.0.50", "255.255.255.0", "192.168.0.1", "8.8.8.8")
