"""machine falso (Pin, PWM, UART, I2C) para rodar o firmware no PC.
Valida os pinos contra o mapeamento real do RP2040 e registra tudo em `reg`."""
import relogio


from relogio import FimDoTrajeto  # noqa: F401  (reexportado)


class Registro:
    def __init__(self):
        self.reset()

    def reset(self):
        self.pwm = []          # (ms, freq, duty)
        self.led = []          # (ms, estado)
        self.uart = None
        self.i2c = None
        self.nmea = []         # fila de (inicio_ms, fim_ms, bytes)
        self.perdidas = 0      # linhas descartadas por estouro do rxbuf
        self.atraso_max = 0    # ms entre a linha chegar inteira e o firmware ler
        self.lidas = 0
        self.fixes_enviados = 0


reg = Registro()

# Pinos válidos no RP2040 (datasheet, tabela de funções GPIO)
UART_TX = {0: (0, 12, 16, 28), 1: (4, 8, 20, 24)}
UART_RX = {0: (1, 13, 17, 29), 1: (5, 9, 21, 25)}
I2C_SDA = {0: (0, 4, 8, 12, 16, 20), 1: (2, 6, 10, 14, 18, 26)}
I2C_SCL = {0: (1, 5, 9, 13, 17, 21), 1: (3, 7, 11, 15, 19, 27)}


class Pin:
    IN, OUT = 0, 1
    PULL_UP, PULL_DOWN = 1, 2

    def __init__(self, id, mode=-1, pull=-1, value=None):
        if not (id == "LED" or (isinstance(id, int) and 0 <= id <= 29)):
            raise ValueError("pino inválido: %r" % (id,))
        self.id = id
        self._v = 0 if value is None else value

    def _set(self, v):
        self._v = 1 if v else 0
        if self.id == "LED":
            reg.led.append((relogio.agora_ms, self._v))

    def on(self):
        self._set(1)

    def off(self):
        self._set(0)

    def toggle(self):
        self._set(not self._v)

    def value(self, v=None):
        if v is None:
            return self._v
        self._set(v)

    def __call__(self, v=None):
        return self.value(v)


class PWM:
    def __init__(self, pin, freq=None, duty_u16=None):
        if pin.id == "LED":
            raise ValueError("o LED do Pico W fica no chip Wi-Fi, não tem PWM")
        self.pin = pin
        self._freq = 0
        self._duty = 0
        if freq is not None:
            self.freq(freq)
        if duty_u16 is not None:
            self.duty_u16(duty_u16)

    def freq(self, f=None):
        if f is None:
            return self._freq
        if not 8 <= f <= 62500000:
            raise ValueError("freq fora da faixa do rp2: %r" % f)
        self._freq = int(f)

    def duty_u16(self, d=None):
        if d is None:
            return self._duty
        if not 0 <= d <= 65535:
            raise ValueError("duty_u16 fora de 0..65535: %r" % d)
        self._duty = int(d)
        reg.pwm.append((relogio.agora_ms, self._freq, self._duty))

    def deinit(self):
        self._duty = 0


class UART:
    def __init__(self, id, baudrate=115200, bits=8, parity=None, stop=1, tx=None, rx=None,
                 timeout=0, timeout_char=0, rxbuf=256, **kw):
        if id not in (0, 1):
            raise ValueError("UART(%r) não existe" % id)
        if tx is not None and tx.id not in UART_TX[id]:
            raise ValueError("GP%s não é TX da UART%d (use %s)" % (tx.id, id, UART_TX[id]))
        if rx is not None and rx.id not in UART_RX[id]:
            raise ValueError("GP%s não é RX da UART%d (use %s)" % (rx.id, id, UART_RX[id]))
        self.baudrate = baudrate
        self.timeout = timeout
        self.rxbuf = rxbuf
        reg.uart = self
        # Antes do UART existir, o que o GPS mandou se perdeu.
        while reg.nmea and reg.nmea[0][0] < relogio.agora_ms:
            reg.nmea.pop(0)
        reg.fixes_enviados = sum(1 for _, _, l in reg.nmea
                                 if l[3:6] == b"RMC" and l.split(b",")[2:3] == [b"A"])

    def _descartar_estouro(self):
        # O rxbuf é um buffer circular alimentado por interrupção: o que não cabe é perdido.
        # Aproximação: perde a linha inteira (na placa sobraria um pedaço, que o checksum descarta).
        ocupado = 0
        i = 0
        while i < len(reg.nmea) and reg.nmea[i][1] <= relogio.agora_ms:
            tam = len(reg.nmea[i][2])
            if ocupado + tam > self.rxbuf:
                del reg.nmea[i]
                reg.perdidas += 1
                continue
            ocupado += tam
            i += 1

    def _entregar(self):
        ini, fim, linha = reg.nmea.pop(0)
        reg.atraso_max = max(reg.atraso_max, relogio.agora_ms - fim)
        reg.lidas += 1
        return linha

    def readline(self):
        self._descartar_estouro()
        if not reg.nmea:
            raise FimDoTrajeto()
        ini, fim, _ = reg.nmea[0]
        if fim <= relogio.agora_ms:
            return self._entregar()
        if ini <= relogio.agora_ms + self.timeout:
            relogio.agora_ms = int(fim) + 1  # começou a chegar dentro do timeout: espera a linha inteira
            return self._entregar()
        relogio.avancar(self.timeout)
        return None

    def any(self):
        return sum(len(l) for _, f, l in reg.nmea if f <= relogio.agora_ms)

    def write(self, b):
        return len(b)


class I2C:
    def __init__(self, id, scl=None, sda=None, freq=400000):
        if sda is not None and sda.id not in I2C_SDA[id]:
            raise ValueError("GP%s não é SDA do I2C%d" % (sda.id, id))
        if scl is not None and scl.id not in I2C_SCL[id]:
            raise ValueError("GP%s não é SCL do I2C%d" % (scl.id, id))
        reg.i2c = self

    def scan(self):
        return [0x3C]


def freq(f=None):
    return 125000000


def reset():
    raise FimDoTrajeto()
