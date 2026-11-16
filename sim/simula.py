"""Simulador no PC para a lógica do firmware.

  python3 sim/simula.py teste [radares.bin]          -> passa de carro (virtualmente) por radares aleatórios
  python3 sim/simula.py gpx trajeto.gpx [radares.bin] -> reproduz um trajeto gravado e mostra os alertas
"""
import math
import os
import random
import sys
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "firmware"))
import radar as rd  # noqa: E402


def destino(lat, lng, rumo_deg, metros):
    """Ponto a `metros` de distância no rumo dado (aproximação plana, ok para poucos km)."""
    r = math.radians(rumo_deg)
    dlat = metros * math.cos(r) / rd.R_TERRA
    dlng = metros * math.sin(r) / (rd.R_TERRA * math.cos(math.radians(lat)))
    return lat + math.degrees(dlat), lng + math.degrees(dlng)


def passagem(base, alvo, rumo_deg, vel_kmh, antes=1500, depois=400, ruido_m=4.0):
    """Simula uma reta passando pelo radar.
    Devolve (distância do 1º aviso ao grupo do radar ou None, registrou passagem, alertas com sentido errado)."""
    al = rd.Alertador(base)
    vel_ms = vel_kmh / 3.6
    ini = destino(alvo.lat, alvo.lng, (rumo_deg + 180) % 360, antes)
    total = antes + depois
    primeiro_aviso = None
    errados = 0
    t, s = 0.0, 0.0
    while s <= total:
        lat, lng = destino(ini[0], ini[1], rumo_deg, s)
        lat, lng = destino(lat, lng, random.uniform(0, 360), random.uniform(0, ruido_m))
        rumo_gps = (rumo_deg + random.uniform(-3, 3)) % 360
        est = al.atualizar(lat, lng, vel_kmh, rumo_gps, t)
        if est.radar is not None and primeiro_aviso is None and \
                rd.distancia(est.radar.lat, est.radar.lng, alvo.lat, alvo.lng) <= al.RAIO_GRUPO:
            primeiro_aviso = rd.distancia(lat, lng, alvo.lat, alvo.lng)
        r = est.radar
        if r is not None and r.direcao != rd.AMBOS and rd.dif_angulo(r.direcao, rumo_deg) > al.TOL_DIRECAO:
            errados += 1
        t += 1
        s += vel_ms
    return primeiro_aviso, alvo.id in al.passados, errados


def teste(caminho_bin, n=300, semente=42):
    random.seed(semente)
    base = rd.Base(caminho_bin)
    todos = []
    with open(caminho_bin, "rb") as f:
        f.seek(base.ini_reg)
        dados = f.read()
    for i in range(base.n_reg):
        todos.append(rd.Radar(i, *rd.struct.unpack_from(rd.REG, dados, i * rd.TAM_REG)))

    com_dir = [r for r in todos if r.direcao != rd.AMBOS]
    amostra = random.sample(com_dir, min(n, len(com_dir)))
    ok = falso_neg = falso_pos = nao_marcou = 0
    dists = []
    for r in amostra:
        vel = random.choice([40, 60, 80, 110])
        d, marcou, err1 = passagem(base, r, r.direcao, vel)
        if d is None:
            falso_neg += 1
        else:
            ok += 1
            dists.append((vel, d))
            if not marcou:
                nao_marcou += 1
        # Sentido contrário: nenhum radar do sentido oposto pode alertar
        _, _, err2 = passagem(base, r, (r.direcao + 180) % 360, vel)
        if err1 or err2:
            falso_pos += 1

    print("Radares testados (com sentido):", len(amostra))
    print("  alertou no sentido certo:      %d" % ok)
    print("  NÃO alertou (falso negativo):  %d" % falso_neg)
    print("  alertou radar do sentido errado: %d" % falso_pos)
    print("  não registrou a passagem:      %d" % nao_marcou)
    for v in (40, 60, 80, 110):
        ds = [d for vv, d in dists if vv == v]
        if ds:
            print("  %3d km/h: 1º aviso a %4.0f m em média (%.1f s antes)" % (
                v, sum(ds) / len(ds), sum(ds) / len(ds) / (v / 3.6)))
    return falso_neg == 0 and falso_pos == 0


def gpx(caminho_gpx, caminho_bin):
    base = rd.Base(caminho_bin)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    pts = ET.parse(caminho_gpx).getroot().findall(".//g:trkpt", ns)
    al = rd.Alertador(base)
    ant, nivel_ant = None, rd.NADA
    for i, p in enumerate(pts):
        lat, lng = float(p.get("lat")), float(p.get("lon"))
        t = float(i)  # assume 1 ponto por segundo
        if ant is None:
            ant = (lat, lng)
            continue
        vel = rd.distancia(ant[0], ant[1], lat, lng) * 3.6
        rumo_deg = rd.rumo(ant[0], ant[1], lat, lng)
        ant = (lat, lng)
        est = al.atualizar(lat, lng, vel, rumo_deg, t)
        if est.nivel != nivel_ant:
            print("t=%5ds vel=%3.0f km/h  %s" % (t, vel, est))
            nivel_ant = est.nivel


if __name__ == "__main__":
    padrao = os.path.join(AQUI, "radares.bin")
    if len(sys.argv) >= 2 and sys.argv[1] == "gpx":
        gpx(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else padrao)
    else:
        sys.exit(0 if teste(sys.argv[2] if len(sys.argv) > 2 else padrao) else 1)
