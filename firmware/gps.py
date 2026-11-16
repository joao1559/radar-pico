# Leitor NMEA mínimo: só a sentença RMC ($GPRMC / $GNRMC), que já traz posição, velocidade e rumo.


def _checksum_ok(linha):
    try:
        corpo, cs = linha[1:].split("*", 1)
        calc = 0
        for c in corpo:
            calc ^= ord(c)
        return calc == int(cs[:2], 16)
    except (ValueError, IndexError):
        return False


def _graus(valor, hemisferio):
    if not valor:
        return None
    ponto = valor.index(".")
    g = float(valor[: ponto - 2]) + float(valor[ponto - 2:]) / 60
    return -g if hemisferio in ("S", "W") else g


def ler_rmc(linha):
    """Devolve (lat, lng, vel_kmh, rumo_deg) ou None se não for RMC válida com fix."""
    if not linha.startswith("$") or linha[3:6] != "RMC" or not _checksum_ok(linha):
        return None
    p = linha.split("*")[0].split(",")
    if len(p) < 9 or p[2] != "A":  # A = fix válido, V = sem fix
        return None
    lat = _graus(p[3], p[4])
    lng = _graus(p[5], p[6])
    if lat is None or lng is None:
        return None
    vel = float(p[7]) * 1.852 if p[7] else 0.0  # nós -> km/h
    rumo = float(p[8]) if p[8] else 0.0
    return lat, lng, vel, rumo
