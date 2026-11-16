"""Roda o firmware/main.py INTEIRO no PC, com hardware falso (sim/fake/) e relógio virtual.

O GPS falso manda NMEA como um NEO-6M de verdade (RMC + VTG/GGA/GSA/GSV/GLL, 1 Hz, 9600 baud).
O buzzer, o LED e o OLED são registrados. Assim dá pra ver o que a placa faria sem ter a placa.

  python3 sim/simula.py placa [-v]                 -> cenários automáticos; exit 1 se algum falhar
  python3 sim/simula.py placa trajeto.gpx [-v]     -> roda o firmware sobre um trajeto gravado

Não mede: consumo de RAM nem tempo de CPU do Pico (no PC o processamento é instantâneo).
"""
import importlib
import math
import os
import random
import sys
import tempfile
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(AQUI, "..", "firmware")
FAKE = os.path.join(AQUI, "fake")
for p in (FIRMWARE, FAKE):  # FAKE fica na frente: machine/network/ssd1306 falsos
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

import machine  # noqa: E402
import network  # noqa: E402
import relogio  # noqa: E402
import ssd1306  # noqa: E402
import radar as rd  # noqa: E402

# Sons do main.py: (frequência, vezes) -> nome
SONS = {(1500, 2): "BOOT", (1800, 1): "AVISO", (2200, 2): "PERTO", (3000, 1): "EXCESSO", (400, 1): "SEM_BASE"}


# ---------------------------------------------------------------- NMEA falso
def _nmea(corpo):
    cs = 0
    for c in corpo:
        cs ^= ord(c)
    return ("$%s*%02X\r\n" % (corpo, cs)).encode()


def _ddmm(v, lat):
    g = int(abs(v))
    m = (abs(v) - g) * 60
    txt = ("%02d%08.5f" if lat else "%03d%08.5f") % (g, m)
    return txt, ("N" if v >= 0 else "S") if lat else ("E" if v >= 0 else "W")


def rajada(seg, ponto):
    """As sentenças que um NEO-6M manda num segundo (~480 bytes). ponto=None -> sem fix."""
    hora = "%02d%02d%02d.00" % (12 + seg // 3600, seg // 60 % 60, seg % 60)
    gsv = [_nmea("GPGSV,3,%d,11,%02d,45,120,38,%02d,30,200,35,%02d,15,310,30,%02d,60,040,41" %
                 (i + 1, 4 * i + 1, 4 * i + 2, 4 * i + 3, 4 * i + 4)) for i in range(3)]
    if ponto is None:
        return [_nmea("GPRMC,%s,V,,,,,,,161126,,,N" % hora), _nmea("GPVTG,,,,,,,,,N"),
                _nmea("GPGGA,%s,,,,,0,00,99.99,,,,,," % hora), _nmea("GPGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99")
                ] + gsv + [_nmea("GPGLL,,,,,%s,V,N" % hora)]
    lat, lng, vel, rumo = ponto
    la, ha = _ddmm(lat, True)
    lo, ho = _ddmm(lng, False)
    nos = vel / 1.852
    return [
        _nmea("GPRMC,%s,A,%s,%s,%s,%s,%.3f,%.2f,161126,,,A" % (hora, la, ha, lo, ho, nos, rumo)),
        _nmea("GPVTG,%.2f,T,,M,%.3f,N,%.3f,K,A" % (rumo, nos, vel)),
        _nmea("GPGGA,%s,%s,%s,%s,%s,1,08,1.01,760.0,M,-5.0,M,," % (hora, la, ha, lo, ho)),
        _nmea("GPGSA,A,3,01,02,03,04,05,06,07,08,,,,,1.80,1.01,1.49"),
    ] + gsv + [_nmea("GPGLL,%s,%s,%s,%s,%s,A,A" % (la, ha, lo, ho, hora))]


def agendar(pontos, t0_ms=1000, baud=9600, lixo_cada=37):
    """Fila de (início_ms, fim_ms, linha) como chegaria na UART. De vez em quando manda lixo
    (bytes inválidos em UTF-8, como na partida do GPS) para exercitar o tratamento de erro."""
    fila = []
    for k, p in enumerate(pontos):
        t = t0_ms + k * 1000 + 40
        linhas = rajada(k, p)
        if lixo_cada and k % lixo_cada == 5:
            linhas = [b"\xff\xfe\x00$GP\xb5b\r\n"] + linhas
        for linha in linhas:
            dur = len(linha) * 10 * 1000 // baud + 1
            fila.append((t, t + dur, linha))
            t += dur
    return fila


# ---------------------------------------------------------------- trajetos
def destino(lat, lng, rumo_deg, metros):
    r = math.radians(rumo_deg)
    return (lat + math.degrees(metros * math.cos(r) / rd.R_TERRA),
            lng + math.degrees(metros * math.sin(r) / (rd.R_TERRA * math.cos(math.radians(lat)))))


def reta(lat, lng, rumo_deg, perfil, antes=1500, depois=500, ruido_m=3.0, rnd=None):
    """Reta passando por (lat,lng). perfil(d) -> km/h, d = metros que faltam (negativo depois)."""
    rnd = rnd or random.Random(1)
    ini = destino(lat, lng, (rumo_deg + 180) % 360, antes)
    pts, s = [], 0.0
    while s <= antes + depois:
        vel = perfil(antes - s)
        a, b = destino(ini[0], ini[1], rumo_deg, s)
        a, b = destino(a, b, rnd.uniform(0, 360), rnd.uniform(0, ruido_m))
        pts.append((a, b, vel, (rumo_deg + rnd.uniform(-2, 2)) % 360))
        s += vel / 3.6
    return pts, ini


def boot(ini, sem_fix=25, parado=3):
    """Liga no carro: alguns segundos sem fix, depois parado, depois começa a andar."""
    return [None] * sem_fix + [(ini[0], ini[1], 0.0, 0.0)] * parado


def carregar_todos(caminho_bin):
    base = rd.Base(caminho_bin)
    with open(caminho_bin, "rb") as f:
        f.seek(base.ini_reg)
        dados = f.read()
    base.f.close()
    return [rd.Radar(i, *rd.struct.unpack_from(rd.REG, dados, i * rd.TAM_REG)) for i in range(base.n_reg)]


def isolado(r, todos, raio=3000):
    """Nenhum outro radar (fora o grupo de faixas) a menos de `raio` m: o cenário fica limpo."""
    for o in todos:
        if o.id != r.id and abs(o.lat - r.lat) < 0.03 and abs(o.lng - r.lng) < 0.03:
            d = rd.distancia(r.lat, r.lng, o.lat, o.lng)
            if rd.Alertador.RAIO_GRUPO < d < raio:
                return False
    return True


# ---------------------------------------------------------------- execução
class Captura:
    """Pega o print() do firmware com o instante virtual."""

    def __init__(self):
        self.linhas, self._buf = [], ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            l, self._buf = self._buf.split("\n", 1)
            self.linhas.append((relogio.agora_ms, l))

    def flush(self):
        pass


def _sons(pwm):
    bipes, ini = [], None
    for t, f, d in pwm:
        if d > 0 and ini is None:
            ini = (t, f)
        elif d == 0 and ini is not None:
            bipes.append((ini[0], ini[1], t - ini[0]))
            ini = None
    sons = []  # agrupa bipes repetidos (ex.: 2 bipes de 2200 = PERTO)
    for t, f, dur in bipes:
        if sons and sons[-1][1] == f and t - sons[-1][3] <= 150:
            sons[-1][2] += 1
            sons[-1][3] = t + dur
        else:
            sons.append([t, f, 1, t + dur])
    return [(t, SONS.get((f, n), "%dHz x%d" % (f, n))) for t, f, n, _ in sons]


def rodar(pontos, dir_base, oled=True, wifi=False):
    machine.reg.reset()
    del ssd1306.quadros[:], ssd1306.erros[:], network.log[:]
    ssd1306.presente = oled
    network.conecta = wifi

    chamadas = []
    orig_atualizar, orig_base = rd.Alertador.atualizar, rd.Base.__init__
    abertas = []

    def atualizar(self, *a):
        est = orig_atualizar(self, *a)
        chamadas.append((relogio.agora_ms, est.nivel))
        return est

    def base_init(self, caminho):
        orig_base(self, caminho)
        abertas.append(self.f)

    rd.Alertador.atualizar, rd.Base.__init__ = atualizar, base_init
    machine.reg.nmea = agendar(pontos)
    fim_nmea = machine.reg.nmea[-1][1] if machine.reg.nmea else 0
    relogio.instalar(800)  # o main.py começa ~0,8 s depois de ligar
    relogio.limite_ms = max(fim_nmea, 0) + 60000
    cap, stdout_orig, cwd = Captura(), sys.stdout, os.getcwd()
    erro = None
    try:
        os.chdir(dir_base)
        sys.stdout = cap
        for m in ("main", "atualiza"):
            sys.modules.pop(m, None)
        importlib.import_module("main")
    except relogio.FimDoTrajeto:
        pass
    except Exception as e:  # o firmware quebrou: é exatamente o que queremos pegar
        import traceback
        erro = traceback.format_exc()
    finally:
        sys.stdout = stdout_orig
        os.chdir(cwd)
        relogio.limite_ms = None
        relogio.desinstalar()
        rd.Alertador.atualizar, rd.Base.__init__ = orig_atualizar, orig_base
        for f in abertas:
            f.close()

    led = machine.reg.led
    return {
        "erro": erro, "prints": cap.linhas, "sons": _sons(machine.reg.pwm), "fixes": len(chamadas),
        "fixes_enviados": machine.reg.fixes_enviados, "perdidas": machine.reg.perdidas,
        "atraso_max": machine.reg.atraso_max, "erros_tela": list(ssd1306.erros),
        "quadros": len(ssd1306.quadros), "led": led, "wifi": list(network.log),
    }


def linha_do_tempo(res, verboso=False):
    evs = [(t, "    " + l) for t, l in res["prints"]]
    evs += [(t, ">>> bipe %s" % n) for t, n in res["sons"]]
    evs.sort(key=lambda e: e[0])
    titulo_ant = None
    for t, txt in evs:
        if not verboso and txt.startswith("    "):
            titulo = txt.split(" | ")[0]
            if titulo == titulo_ant:
                continue
            titulo_ant = titulo
        print("  t=%6.1fs %s" % (t / 1000.0, txt))


def pisca_led(res, ate_ms):
    """Trocas por segundo do LED enquanto não tem fix (o main.py promete 'piscando')."""
    trocas = [t for t, _ in res["led"] if 6000 <= t <= ate_ms]
    seg = (ate_ms - 6000) / 1000.0
    return len(trocas) / seg if seg > 0 else 0


def checar(nome, res, esperado, extra=None, verboso=False):
    print("\n=== %s ===" % nome)
    linha_do_tempo(res, verboso)
    falhas = []
    if res["erro"]:
        falhas.append("firmware levantou exceção:\n" + res["erro"])
    sons = [n for _, n in res["sons"]]
    i = 0
    for n in sons:  # `esperado` tem que aparecer nessa ordem (pode haver repetições no meio)
        if i < len(esperado) and n == esperado[i]:
            i += 1
    if i < len(esperado):
        falhas.append("sons esperados %s, tocou %s" % (esperado, sons))
    if any(t for t, l in res["prints"] if l.startswith("Atualizacao | erro")):
        falhas.append("atualiza.py deu erro no boot")
    if res["perdidas"]:
        falhas.append("%d linhas NMEA perdidas (rxbuf estourou)" % res["perdidas"])
    if res["fixes_enviados"] and res["fixes"] != res["fixes_enviados"]:
        falhas.append("processou %d de %d fixes" % (res["fixes"], res["fixes_enviados"]))
    falhas += res["erros_tela"]
    if extra:
        falhas += [f for f in extra(res) if f]
    print("  -- fixes %d/%d, linhas perdidas %d, atraso máx. de leitura %d ms, %d quadros no OLED" % (
        res["fixes"], res["fixes_enviados"], res["perdidas"], res["atraso_max"], res["quadros"]))
    for f in falhas:
        print("  FALHOU: " + f)
    if not falhas:
        print("  OK")
    return not falhas


def cenarios(caminho_bin, verboso=False):
    rnd = random.Random(7)
    dir_base = os.path.dirname(os.path.abspath(caminho_bin))
    if os.path.basename(caminho_bin) != "radares.bin":
        raise SystemExit("o main.py abre 'radares.bin': passe um arquivo com esse nome")
    todos = carregar_todos(caminho_bin)
    fixos = [r for r in todos if r.tipo == rd.FIXO and r.direcao != rd.AMBOS and 40 <= r.limite <= 80]
    rnd.shuffle(fixos)
    alvo = next(r for r in fixos if isolado(r, todos))
    lim = alvo.limite
    print("Radar escolhido: id %d em %.5f,%.5f, %d km/h, sentido %d°" % (
        alvo.id, alvo.lat, alvo.lng, lim, alvo.direcao))
    ok = True

    def com_boot(pts_ini):
        pts, ini = pts_ini
        return boot(ini) + pts

    # 1) Dentro do limite: aviso e depois "perto"
    pts = com_boot(reta(alvo.lat, alvo.lng, alvo.direcao, lambda d: lim - 10, rnd=rnd))
    fim_sem_fix = 1000 + 25 * 1000
    res = rodar(pts, dir_base)
    hz = pisca_led(res, fim_sem_fix)
    ok &= checar("dentro do limite (%d km/h)" % (lim - 10), res, ["BOOT", "AVISO", "PERTO"], verboso=verboso,
                 extra=lambda r: [
                     None if any(l.startswith("Livre") for _, l in r["prints"]) else "não mostrou 'Livre' depois",
                     None if 0.3 <= hz <= 5 else "LED sem fix troca %.1f vezes/s (esperado ~1)" % hz,
                     None if any(l.startswith("SEM GPS") for _, l in r["prints"]) else "não mostrou 'SEM GPS'",
                 ])

    # 2) Acelera perto do radar: aviso, depois excesso repetido
    pts = com_boot(reta(alvo.lat, alvo.lng, alvo.direcao,
                        lambda d: lim + 15 if -50 < d < 250 else lim - 10, rnd=rnd))
    res = rodar(pts, dir_base)
    ok &= checar("acelera a %d km/h perto do radar" % (lim + 15), res, ["BOOT", "AVISO", "EXCESSO", "EXCESSO"],
                 verboso=verboso,
                 extra=lambda r: [None if any("REDUZA" in l for _, l in r["prints"]) else "não mostrou REDUZA"])

    # 3) Sentido contrário: não pode tocar nada além do boot
    pts = com_boot(reta(alvo.lat, alvo.lng, (alvo.direcao + 180) % 360, lambda d: lim + 20, rnd=rnd))
    res = rodar(pts, dir_base)
    ok &= checar("sentido contrário", res, ["BOOT"], verboso=verboso,
                 extra=lambda r: [None if len(r["sons"]) == 1 else "tocou %s" % [n for _, n in r["sons"]]])

    # 4) Sem OLED ligado: tem que funcionar igual (só pelo som)
    pts = com_boot(reta(alvo.lat, alvo.lng, alvo.direcao, lambda d: lim - 10, rnd=rnd))
    res = rodar(pts, dir_base, oled=False)
    ok &= checar("sem OLED", res, ["BOOT", "AVISO", "PERTO"], verboso=verboso,
                 extra=lambda r: [None if r["quadros"] == 0 else "desenhou na tela inexistente"])

    # 5) Radar de trecho acima da média
    trechos = [r for r in todos if r.tipo == rd.TRECHO and r.fim and r.limite and
               rd.distancia(r.lat, r.lng, r.fim[0], r.fim[1]) > 500]
    trechos = [r for r in trechos if r.direcao == rd.AMBOS or
               rd.dif_angulo(r.direcao, rd.rumo(r.lat, r.lng, r.fim[0], r.fim[1])) <= 30]
    if trechos:
        tr = trechos[0]
        rumo_tr = rd.rumo(tr.lat, tr.lng, tr.fim[0], tr.fim[1])
        comp = rd.distancia(tr.lat, tr.lng, tr.fim[0], tr.fim[1])
        pts = com_boot(reta(tr.lat, tr.lng, rumo_tr, lambda d: tr.limite + 20, depois=comp + 300, rnd=rnd))
        res = rodar(pts, dir_base)
        ok &= checar("trecho de %.1f km a %d km/h (limite %d)" % (comp / 1000, tr.limite + 20, tr.limite), res,
                     ["BOOT", "EXCESSO"], verboso=verboso,
                     extra=lambda r: [None if any("media" in l for _, l in r["prints"]) else "não mostrou a média"])
    else:
        print("\n(sem radar de trecho utilizável na base; cenário pulado)")

    # 6) Sem base: avisa e fica bipando grave, sem travar
    with tempfile.TemporaryDirectory() as vazio:
        res = rodar([], vazio)
    ok &= checar("sem radares.bin", res, ["SEM_BASE", "SEM_BASE"], verboso=verboso,
                 extra=lambda r: [None if any(l.startswith("SEM BASE") for _, l in r["prints"]) else "sem aviso na tela"])

    print("\n%s" % ("TODOS OS CENÁRIOS OK" if ok else "HÁ FALHAS"))
    return ok


def gpx(caminho_gpx, caminho_bin, verboso=False):
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    pts_xml = ET.parse(caminho_gpx).getroot().findall(".//g:trkpt", ns)
    pontos, ant = [], None
    for p in pts_xml:
        lat, lng = float(p.get("lat")), float(p.get("lon"))
        if ant is None:
            pontos.append((lat, lng, 0.0, 0.0))
        else:
            pontos.append((lat, lng, rd.distancia(ant[0], ant[1], lat, lng) * 3.6, rd.rumo(ant[0], ant[1], lat, lng)))
        ant = (lat, lng)
    res = rodar(boot(pontos[0][:2]) + pontos, os.path.dirname(os.path.abspath(caminho_bin)))
    return checar(os.path.basename(caminho_gpx), res, ["BOOT"], verboso=verboso)


def principal(args, padrao_bin):
    verboso = "-v" in args
    args = [a for a in args if a != "-v"]
    gpxs = [a for a in args if a.lower().endswith(".gpx")]
    bins = [a for a in args if a.lower().endswith(".bin")]
    caminho_bin = bins[0] if bins else padrao_bin
    if gpxs:
        return gpx(gpxs[0], caminho_bin, verboso)
    return cenarios(caminho_bin, verboso)
