# Base de radares + lógica de alerta.
# Só usa math/struct, então roda igual no MicroPython (Pico W) e no CPython (simulador).
import math
import struct

CAB = "<4sHHII"
IDX = "<IIH"
REG = "<iiBBHhh"
TAM_CAB = struct.calcsize(CAB)  # 16
TAM_IDX = struct.calcsize(IDX)  # 10
TAM_REG = struct.calcsize(REG)  # 16

FIXO, TRECHO, SEMAFORO = 0, 1, 2
AMBOS = 0xFFFF
R_TERRA = 6371000.0

# Níveis de alerta
NADA, AVISO, PERTO, EXCESSO = 0, 1, 2, 3


class Radar:
    def __init__(self, id, lat, lng, limite, tipo, direcao, dlat, dlng):
        self.id = id
        self.lat = lat / 1e6
        self.lng = lng / 1e6
        self.limite = limite  # 0 = desconhecido
        self.tipo = tipo
        self.direcao = direcao
        self.fim = None
        if tipo == TRECHO and (dlat or dlng):
            self.fim = (self.lat + dlat / 1e4, self.lng + dlng / 1e4)


class Base:
    """Lê o radares.bin direto do arquivo (busca binária no índice), sem carregar tudo na RAM."""

    def __init__(self, caminho):
        self.f = open(caminho, "rb")
        magic, versao, self.div, self.n_cel, self.n_reg = struct.unpack(CAB, self.f.read(TAM_CAB))
        if magic != b"PRDL" or versao != 1:
            raise ValueError("radares.bin inválido")
        self.ini_reg = TAM_CAB + self.n_cel * TAM_IDX
        self._cache_cel = None
        self._cache = []  # [(primeiro_id, bytes)]

    def _celula(self, clat, clng):
        return clat * 360 * self.div + clng

    def _busca(self, cel):
        lo, hi = 0, self.n_cel - 1
        f = self.f
        while lo <= hi:
            m = (lo + hi) // 2
            f.seek(TAM_CAB + m * TAM_IDX)
            c, prim, qtd = struct.unpack(IDX, f.read(TAM_IDX))
            if c == cel:
                return prim, qtd
            if c < cel:
                lo = m + 1
            else:
                hi = m - 1
        return None

    def proximos(self, lat, lng, margem=1500):
        """Gera (id, campos) dos radares nas células a menos de `margem` metros.
        Guarda só os bytes crus em cache (16 B por radar), para caber na RAM do Pico."""
        fl = (lat + 90) * self.div
        fg = (lng + 180) * self.div
        clat, clng = int(math.floor(fl)), int(math.floor(fg))
        m_cel_lat = 111320.0 / self.div
        m_cel_lng = m_cel_lat * math.cos(math.radians(lat))
        dls = [0]
        if (fl - clat) * m_cel_lat < margem:
            dls.append(-1)
        if (clat + 1 - fl) * m_cel_lat < margem:
            dls.append(1)
        dgs = [0]
        if (fg - clng) * m_cel_lng < margem:
            dgs.append(-1)
        if (clng + 1 - fg) * m_cel_lng < margem:
            dgs.append(1)
        chave = tuple(sorted(self._celula(clat + a, clng + b) for a in dls for b in dgs))
        if chave != self._cache_cel:
            self._cache = []  # libera antes de ler o novo
            pedacos = []
            for cel in chave:
                achou = self._busca(cel)
                if achou:
                    prim, qtd = achou
                    self.f.seek(self.ini_reg + prim * TAM_REG)
                    pedacos.append((prim, self.f.read(qtd * TAM_REG)))
            self._cache_cel = chave
            self._cache = pedacos
        for prim, dados in self._cache:
            for i in range(len(dados) // TAM_REG):
                yield prim + i, struct.unpack_from(REG, dados, i * TAM_REG)


def distancia(lat1, lng1, lat2, lng2):
    """Equiretangular: erro desprezível em poucos km, e bem mais barata que haversine."""
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return R_TERRA * math.sqrt(x * x + y * y)


def rumo(lat1, lng1, lat2, lng2):
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.degrees(math.atan2(x, y)) % 360


def dif_angulo(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


class Estado:
    def __init__(self):
        self.nivel = NADA
        self.radar = None
        self.dist = 0
        self.media_trecho = None  # km/h, quando dentro de radar de trecho

    def __repr__(self):
        r = self.radar
        return "nivel=%d dist=%dm limite=%s tipo=%s media=%s" % (
            self.nivel, self.dist, r.limite if r else "-", r.tipo if r else "-", self.media_trecho)


class Alertador:
    # Ajustes
    SEGUNDOS_AVISO = 15      # avisa ~15 s antes de chegar
    DIST_MIN_AVISO = 300     # nunca avisa a menos de 300 m
    DIST_MAX_AVISO = 1200
    SEGUNDOS_PERTO = 6
    DIST_MIN_PERTO = 120
    TOL_DIRECAO = 45         # radar com sentido: aceita ±45° do seu rumo
    TOL_A_FRENTE = 30        # radar precisa estar num cone de ±30° à frente
    VEL_MIN = 10             # km/h; abaixo disso o rumo do GPS é ruído
    TOLERANCIA_KMH = 0       # margem acima do limite antes do alerta de excesso
    RAIO_GRUPO = 60          # m; radares mais próximos que isso contam como um só
    ESQUECER_APOS = 180      # s; depois disso um radar já passado pode alertar de novo

    def __init__(self, base):
        self.base = base
        self.passados = {}     # id -> instante em que passou
        self.alvo = None
        self.dist_ant = None
        self.trecho = None     # [radar, metros percorridos, segundos, dist_reta]
        self.t_ant = None

    def atualizar(self, lat, lng, vel_kmh, rumo_deg, t):
        """Chamar a cada leitura válida do GPS. t em segundos (monotônico)."""
        est = Estado()
        dt = 0 if self.t_ant is None else max(0, t - self.t_ant)
        self.t_ant = t
        self._limpar(t)
        self._atualiza_trecho(lat, lng, vel_kmh, dt, est)

        vel_ms = vel_kmh / 3.6
        alcance = min(self.DIST_MAX_AVISO, max(self.DIST_MIN_AVISO, vel_ms * self.SEGUNDOS_AVISO))

        # Segue o alvo atual até passar por ele
        if self.alvo is not None:
            d = distancia(lat, lng, self.alvo.lat, self.alvo.lng)
            passou = self.dist_ant is not None and d > self.dist_ant + 3 and \
                dif_angulo(rumo(lat, lng, self.alvo.lat, self.alvo.lng), rumo_deg) > 90
            if passou or d > alcance + 300:
                if passou:
                    self._marcar_grupo(self.alvo, t)
                    self._inicia_trecho(self.alvo, lat, lng)
                self.alvo, self.dist_ant = None, None
            else:
                self.dist_ant = d

        if self.alvo is None and vel_kmh >= self.VEL_MIN:
            self.alvo = self._escolher(lat, lng, rumo_deg, alcance)
            if self.alvo is not None:
                self.dist_ant = distancia(lat, lng, self.alvo.lat, self.alvo.lng)

        if self.alvo is not None:
            r = self.alvo
            est.radar, est.dist = r, self.dist_ant
            perto = max(self.DIST_MIN_PERTO, vel_ms * self.SEGUNDOS_PERTO)
            est.nivel = PERTO if self.dist_ant <= perto else AVISO
            if r.limite and vel_kmh > r.limite + self.TOLERANCIA_KMH:
                est.nivel = EXCESSO

        if est.media_trecho is not None and self.trecho[0].limite and \
                est.media_trecho > self.trecho[0].limite + self.TOLERANCIA_KMH:
            est.nivel = EXCESSO
            if est.radar is None:
                est.radar = self.trecho[0]
        return est

    def _escolher(self, lat, lng, rumo_deg, alcance):
        # Pré-filtro por caixa em inteiros (barato) antes de qualquer conta em float.
        clat, clng = int(lat * 1e6), int(lng * 1e6)
        jl = int(alcance / 111320 * 1e6)
        jg = int(jl / max(0.1, math.cos(math.radians(lat))))
        melhor, melhor_d = None, alcance
        for id, c in self.base.proximos(lat, lng):
            if abs(c[0] - clat) > jl or abs(c[1] - clng) > jg or id in self.passados:
                continue
            rlat, rlng, direcao = c[0] / 1e6, c[1] / 1e6, c[4]
            d = distancia(lat, lng, rlat, rlng)
            if d > melhor_d:
                continue
            if direcao != AMBOS and dif_angulo(direcao, rumo_deg) > self.TOL_DIRECAO:
                continue
            if d > 30 and dif_angulo(rumo(lat, lng, rlat, rlng), rumo_deg) > self.TOL_A_FRENTE:
                continue
            melhor, melhor_d = (id, c), d
        return Radar(melhor[0], *melhor[1]) if melhor else None

    def _marcar_grupo(self, alvo, t):
        # Radares de várias faixas ficam a poucos metros um do outro: um alerta vale pelo grupo.
        for id, c in self.base.proximos(alvo.lat, alvo.lng):
            if distancia(alvo.lat, alvo.lng, c[0] / 1e6, c[1] / 1e6) <= self.RAIO_GRUPO:
                self.passados[id] = t

    def _inicia_trecho(self, r, lat, lng):
        if r.tipo == TRECHO and r.fim is not None:
            reta = distancia(r.lat, r.lng, r.fim[0], r.fim[1])
            self.trecho = [r, 0.0, 0.0, reta]

    def _atualiza_trecho(self, lat, lng, vel_kmh, dt, est):
        if self.trecho is None:
            return
        tr = self.trecho
        tr[1] += vel_kmh / 3.6 * dt
        tr[2] += dt
        d_fim = distancia(lat, lng, tr[0].fim[0], tr[0].fim[1])
        # Fim do trecho: chegou no ponto final, ou rodou bem mais do que o trecho (saiu da via).
        if d_fim < 40 or tr[1] > tr[3] * 1.5 + 500:
            self.trecho = None
            return
        if tr[2] >= 5:
            est.media_trecho = tr[1] / tr[2] * 3.6

    def _limpar(self, t):
        velhos = [i for i, tp in self.passados.items() if t - tp > self.ESQUECER_APOS]
        for i in velhos:
            del self.passados[i]
