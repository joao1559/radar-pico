# Roda NO PICO (mpremote run sim/frag_pico.py): teste de resistência acelerado da RAM.
# "Dirige" em círculos por cidades densas, 150 m por passo, para o cache de células trocar muito mais
# vezes do que num carro de verdade, e mede se o heap fragmenta (maior bloco contínuo alocável).
import gc
import math
import time

import gps
import radar

MINUTOS = 20
PASSO_M = 150
R = 6371000.0
CIDADES = [  # centro, raio do círculo (m)
    ("Brasilia", -15.7940, -47.8825, 4000),
    ("SP", -23.5505, -46.6333, 6000),
    ("Rio", -22.9068, -43.1729, 5000),
    ("BH", -19.9167, -43.9345, 4000),
]


def ponto(lat, lng, rumo_deg, m):
    r = math.radians(rumo_deg)
    return (lat + math.degrees(m * math.cos(r) / R),
            lng + math.degrees(m * math.sin(r) / (R * math.cos(math.radians(lat)))))


def nmea(lat, lng, vel, rumo):
    def ddmm(v, n):
        g = int(abs(v))
        return ("%0" + str(n) + "d%08.5f") % (g, (abs(v) - g) * 60)
    corpo = "GPRMC,120000.00,A,%s,%s,%s,%s,%.3f,%.2f,161126,,,A" % (
        ddmm(lat, 2), "S" if lat < 0 else "N", ddmm(lng, 3), "W" if lng < 0 else "E", vel / 1.852, rumo)
    cs = 0
    for c in corpo:
        cs ^= ord(c)
    return ("$%s*%02X\r\n" % (corpo, cs)).encode()  # bytes, como chega da UART


def maior_bloco():
    gc.collect()
    lo, hi = 0, gc.mem_free()
    while hi - lo > 256:
        m = (lo + hi) // 2
        try:
            b = bytearray(m)
            del b
            lo = m
        except MemoryError:
            hi = m
    return lo


base = radar.Base("radares.bin")
al = radar.Alertador(base)
gc.collect()
print("inicio: livre %d B, maior bloco %d B" % (gc.mem_free(), maior_bloco()))
print("min  passos  trocas_cache  livre_B  maior_bloco_B  pior_passo_ms  alertas  erros")

t_ini = time.ticks_ms()
prox_rel = 60000
passos = trocas = alertas = erros = 0
pior = 0
pior_bloco = 1 << 30
cel_ant = None
c = 0
ang = 0.0
t_virtual = 0.0
while time.ticks_diff(time.ticks_ms(), t_ini) < MINUTOS * 60000:
    nome, clat, clng, raio = CIDADES[c]
    lat, lng = ponto(clat, clng, ang, raio)
    rumo = (ang + 90) % 360  # tangente ao círculo
    t0 = time.ticks_ms()
    try:
        fix = gps.ler_rmc(nmea(lat, lng, 60, rumo).decode().strip())
        est = al.atualizar(fix[0], fix[1], fix[2], fix[3], t_virtual)
        if est.radar:  # mesmas strings que o main.py monta para a tela
            txt = " | ".join(("RADAR", "%d km/h" % est.radar.limite, "%d m" % int(est.dist),
                              "voce: %d km/h" % int(fix[2])))
            alertas += 1
        else:
            txt = "Livre | %d km/h" % int(fix[2])
    except MemoryError:
        erros += 1
        gc.collect()
    pior = max(pior, time.ticks_diff(time.ticks_ms(), t0))
    if base._cache_cel != cel_ant:
        trocas += 1
        cel_ant = base._cache_cel
    passos += 1
    t_virtual += PASSO_M / (60 / 3.6)
    ang += math.degrees(PASSO_M / raio)
    if ang >= 360:  # volta completa: próxima cidade
        ang -= 360
        c = (c + 1) % len(CIDADES)
        al.passados = {}
    dt = time.ticks_diff(time.ticks_ms(), t_ini)
    if dt >= prox_rel:
        mb = maior_bloco()
        pior_bloco = min(pior_bloco, mb)
        print("%3d  %6d  %12d  %7d  %13d  %13d  %7d  %5d" % (
            dt // 60000, passos, trocas, gc.mem_free(), mb, pior, alertas, erros))
        pior = 0
        prox_rel += 60000

print("FIM: %d passos, %d trocas de cache, %d MemoryError, menor 'maior bloco' %d B" % (
    passos, trocas, erros, pior_bloco))
