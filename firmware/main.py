# Alerta de radar no carro: Pico W + GPS + buzzer (+ OLED opcional).
import time

from machine import I2C, PWM, UART, Pin

import config
import gps
import radar

led = Pin("LED", Pin.OUT)
buzzer = PWM(Pin(config.BUZZER))
buzzer.duty_u16(0)

# ---------- OLED (opcional: se não tiver o módulo ou a tela, segue sem) ----------
tela = None
try:
    import ssd1306
    tela = ssd1306.SSD1306_I2C(128, 64, I2C(0, sda=Pin(config.OLED_SDA), scl=Pin(config.OLED_SCL)))
except Exception:
    pass


def mostrar(*linhas):
    global tela
    print(" | ".join(linhas))
    if tela is None:
        return
    tela.fill(0)
    for i, l in enumerate(linhas[:6]):
        tela.text(l[:16], 0, i * 11)
    try:
        tela.show()
    except OSError:  # fio da tela soltou (vibração): segue só com o som, sem derrubar o alerta
        tela = None


# ---------- Som ----------
def bipe(freq=2000, ms=120, vezes=1, pausa=80):
    duty = int(65535 * config.VOLUME / 2)
    for i in range(vezes):
        buzzer.freq(freq)
        buzzer.duty_u16(duty)
        time.sleep_ms(ms)
        buzzer.duty_u16(0)
        if i < vezes - 1:
            time.sleep_ms(pausa)


SONS = {
    radar.AVISO: lambda: bipe(1800, 150, 1),
    radar.PERTO: lambda: bipe(2200, 100, 2),
    radar.EXCESSO: lambda: bipe(3000, 250, 1),
}
NOMES = {radar.FIXO: "RADAR", radar.TRECHO: "TRECHO", radar.SEMAFORO: "SEMAFORO"}

# ---------- Atualização pelo Wi-Fi no boot ----------
mostrar("Radar Pico", "procurando Wi-Fi")
try:
    import atualiza
    atualiza.tentar(lambda m: mostrar("Atualizacao", m))
except Exception as e:
    mostrar("Atualizacao", "erro", str(e))

try:
    base = radar.Base("radares.bin")
except OSError:
    mostrar("SEM BASE!", "conecte no Wi-Fi", "e reinicie")
    while True:
        bipe(400, 500)
        time.sleep(5)

alertador = radar.Alertador(base)
alertador.TOLERANCIA_KMH = config.TOLERANCIA_KMH
mostrar("Radar Pico", "%d radares" % base.n_reg, "aguardando GPS")
bipe(1500, 60, 2)

uart = UART(config.GPS_UART, baudrate=config.GPS_BAUD,
            tx=Pin(config.GPS_TX), rx=Pin(config.GPS_RX), timeout=50, rxbuf=2048)

# ---------- Loop principal ----------
nivel_ant = radar.NADA
alvo_ant = None
ultimo_fix = time.ticks_ms()
ultimo_bipe_excesso = 0
ultimo_pisca = 0
sem_fix_avisado = False

while True:
    bruto = uart.readline()
    agora = time.ticks_ms()

    if time.ticks_diff(agora, ultimo_fix) > 5000:
        if time.ticks_diff(agora, ultimo_pisca) >= 500:
            led.toggle()  # LED piscando 1 Hz = sem fix
            ultimo_pisca = agora
        if not sem_fix_avisado:
            mostrar("SEM GPS", "%d radares" % base.n_reg)
            sem_fix_avisado = True

    if not bruto:
        continue
    try:
        fix = gps.ler_rmc(bruto.decode().strip())
    except (UnicodeError, ValueError):
        continue
    if fix is None:
        continue

    lat, lng, vel, rumo_deg = fix
    ultimo_fix = agora
    sem_fix_avisado = False
    led.on()

    est = alertador.atualizar(lat, lng, vel, rumo_deg, agora / 1000)
    alvo = est.radar.id if est.radar else None

    # Som: toca quando o nível sobe ou quando muda de radar; excesso repete a cada 1,5 s.
    if est.nivel != radar.NADA and (est.nivel > nivel_ant or alvo != alvo_ant):
        SONS[est.nivel]()
        ultimo_bipe_excesso = agora
    elif est.nivel == radar.EXCESSO and time.ticks_diff(agora, ultimo_bipe_excesso) > 1500:
        SONS[radar.EXCESSO]()
        ultimo_bipe_excesso = agora

    if est.radar:
        r = est.radar
        lim = ("%d km/h" % r.limite) if r.limite else "limite ?"
        extra = ("media %d" % int(est.media_trecho)) if est.media_trecho else ("%d m" % int(est.dist))
        mostrar(NOMES.get(r.tipo, "RADAR"), lim, extra, "voce: %d km/h" % int(vel),
                "!! REDUZA !!" if est.nivel == radar.EXCESSO else "")
    else:  # sem radar à frente: mostra a velocidade (e tira o "SEM GPS" da tela)
        mostrar("Livre", "%d km/h" % int(vel))

    nivel_ant, alvo_ant = est.nivel, alvo
