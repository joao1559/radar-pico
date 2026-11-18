# Roda NO PICO: acompanha o GPS até ter fix, no console e no OLED.
#   mpremote run sim/gps_pico.py  -> com o PC; para 15 s depois do fix ou em MAX_S
#   SOZINHO = True + copiado como main.py na placa -> roda sem PC (num carregador) até desligar,
#                                    e grava o progresso em gps_log.txt na flash
import time

from machine import I2C, UART, Pin

import gps

SOZINHO = False
MAX_S = 360
LOG = "gps_log.txt"

tela = None
try:
    import ssd1306
    tela = ssd1306.SSD1306_I2C(128, 64, I2C(0, sda=Pin(4), scl=Pin(5)))
except Exception:
    pass


def mostrar(*linhas):
    print(" | ".join(linhas))
    if tela:
        tela.fill(0)
        for i, l in enumerate(linhas[:6]):
            tela.text(l[:16], 0, i * 11)
        tela.show()


def gravar(txt):
    if not SOZINHO:
        return
    try:
        with open(LOG, "a") as f:
            f.write(txt + "\n")
    except OSError:
        pass


u = UART(0, 9600, tx=Pin(0), rx=Pin(1), timeout=50, rxbuf=2048)
t0 = time.ticks_ms()
vistos = {}      # constelação -> satélites em vista (GSV): GP = GPS, BD = BeiDou, GL = GLONASS
usados = 0       # satélites usados no fix (GGA)
hdop = "-"
fix = None
prox = 0
ult_log = -30
primeiro_fix = None
gravar("--- boot")
while SOZINHO or time.ticks_diff(time.ticks_ms(), t0) < MAX_S * 1000:
    b = u.readline()
    if not b:
        continue
    try:
        l = b.decode().strip()
    except UnicodeError:
        continue
    p = l.split("*")[0].split(",")
    if l[3:6] == "GSV" and len(p) > 3 and p[3]:
        vistos[l[1:3]] = int(p[3])
    elif l[3:6] == "GGA" and len(p) > 8:
        usados = int(p[7] or 0)
        hdop = p[8] or "-"
    elif l[3:6] == "RMC":
        f = gps.ler_rmc(l)
        if f and primeiro_fix is None:
            primeiro_fix = time.ticks_diff(time.ticks_ms(), t0) // 1000
            gravar("FIX em %ds: %.5f,%.5f usados %d hdop %s" % (primeiro_fix, f[0], f[1], usados, hdop))
        fix = f
    s = time.ticks_diff(time.ticks_ms(), t0) // 1000
    if s >= prox:
        prox = s + 5
        vis = " ".join("%s%d" % (k, v) for k, v in vistos.items()) or "0"
        if fix:
            mostrar("FIX em %ds" % primeiro_fix, "%.5f" % fix[0], "%.5f" % fix[1],
                    "%d km/h %d gr" % (fix[2], fix[3]), "sat %d hdop %s" % (usados, hdop), "vistos " + vis)
        else:
            mostrar("SEM FIX %ds" % s, "vistos " + vis, "usados %d" % usados)
        if s - ult_log >= 30:
            ult_log = s
            gravar("%ds fix=%s vistos %s usados %d" % (s, "sim" if fix else "nao", vis, usados))
    if not SOZINHO and fix and s >= primeiro_fix + 15:
        break
print("fim: primeiro fix", primeiro_fix, "s")
