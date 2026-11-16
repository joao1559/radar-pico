# Roda NO PICO (mpremote run sim/bench_pico.py): mede tempo por fix e RAM do Alertador real,
# com radar.py e radares.bin que já estão na flash. Não precisa de GPS nem de outros módulos.
import gc
import math
import time

import gps
import radar

R = 6371000.0

LUGARES = [  # nome, lat, lng
    ("Brasilia centro (pior caso: 1326 radares no cache)", -15.8052, -47.8937),
    ("SP centro", -23.5505, -46.6333),
    ("radar isolado (AL)", -9.90415, -36.22269),
]


def destino(lat, lng, rumo_deg, m):
    r = math.radians(rumo_deg)
    return (lat + math.degrees(m * math.cos(r) / R),
            lng + math.degrees(m * math.sin(r) / (R * math.cos(math.radians(lat)))))


def trajeto(nome, lat0, lng0, vel=50, passos=40):
    gc.collect()
    livre_ini = gc.mem_free()
    base = radar.Base("radares.bin")
    al = radar.Alertador(base)
    tempos, livre_min, avisos = [], livre_ini, 0
    for rumo in (0, 90, 180, 270):
        lat, lng = destino(lat0, lng0, (rumo + 180) % 360, passos * vel / 3.6 / 2)
        for i in range(passos):
            t0 = time.ticks_us()
            est = al.atualizar(lat, lng, vel, rumo, time.ticks_ms() / 1000)
            tempos.append(time.ticks_diff(time.ticks_us(), t0))
            livre_min = min(livre_min, gc.mem_free())
            if est.nivel:
                avisos += 1
            lat, lng = destino(lat, lng, rumo, vel / 3.6)
    gc.collect()
    retido = livre_ini - gc.mem_free()
    base.f.close()
    tempos.sort()
    print("%s" % nome)
    print("  %d fixes: mediana %d ms, p95 %d ms, max %d ms | com alerta: %d" % (
        len(tempos), tempos[len(tempos) // 2] // 1000, tempos[len(tempos) * 95 // 100] // 1000,
        tempos[-1] // 1000, avisos))
    print("  RAM: livre antes %d B, minimo durante %d B, retido (cache) %d B" % (livre_ini, livre_min, retido))
    del al, base
    gc.collect()


def nmea():
    linha = "$GPRMC,120000.00,A,2333.03000,S,04637.99800,W,27.000,90.00,161126,,,A*"
    corpo = linha[1:-1]
    cs = 0
    for c in corpo:
        cs ^= ord(c)
    linha += "%02X" % cs
    t0 = time.ticks_us()
    for _ in range(100):
        gps.ler_rmc(linha)
    print("gps.ler_rmc: %d us por sentenca" % (time.ticks_diff(time.ticks_us(), t0) // 100))


gc.collect()
print("RAM livre no inicio: %d B" % gc.mem_free())
nmea()
for l in LUGARES:
    trajeto(*l)
print("fim")
