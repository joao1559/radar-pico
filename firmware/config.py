# Ajuste aqui sem mexer no resto do código.

# Wi-Fi usado só para atualizar a base (garagem ou hotspot do celular)
WIFI_SSID = "minha-rede"
WIFI_SENHA = "minha-senha"
WIFI_TIMEOUT_S = 10
try:  # credenciais reais ficam em segredos.py (fora do git): WIFI_SSID / WIFI_SENHA
    from segredos import *  # noqa: F401,F403
except ImportError:
    pass

# Onde o GitHub Action publica o radares.bin (troque pelo seu repositório)
URL_BASE = "https://raw.githubusercontent.com/joao1559/radar-pico/dados/radares.bin"
URL_VERSAO = URL_BASE + ".versao"

# Pinos
GPS_UART = 0
GPS_TX = 0       # GP0 -> RX do GPS
GPS_RX = 1       # GP1 <- TX do GPS
GPS_BAUD = 9600
BUZZER = 15      # buzzer passivo (PWM)
OLED_SDA = 4     # opcional (SSD1306 128x64, I2C0)
OLED_SCL = 5

TOLERANCIA_KMH = 0   # alerta de excesso só acima de limite + tolerância
VOLUME = 0.5         # 0..1 (duty do PWM)
