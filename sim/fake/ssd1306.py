"""ssd1306 falso: confere se o texto cabe na tela 128x64 e guarda o último quadro."""
presente = True   # False simula placa sem OLED (o construtor falha, como sem o módulo ligado)
solta_apos = None  # N: o show() número N+1 em diante falha (fio da tela soltou com o carro andando)
quadros = []      # cada show() vira uma tupla de linhas
erros = []


class SSD1306_I2C:
    def __init__(self, largura, altura, i2c, addr=0x3C):
        if not presente:
            raise OSError(19, "ENODEV")  # mesmo erro que o I2C dá sem nada no barramento
        self.w, self.h = largura, altura
        self._linhas = {}

    def fill(self, c):
        self._linhas = {}

    def text(self, s, x, y, c=1):
        if x < 0 or y < 0 or x + 8 * len(s) > self.w or y + 8 > self.h:
            erros.append("texto %r em (%d,%d) sai da tela %dx%d" % (s, x, y, self.w, self.h))
        self._linhas[y] = s

    def show(self):
        if solta_apos is not None and len(quadros) >= solta_apos:
            raise OSError(5, "EIO")  # o que o I2C do rp2 levanta quando o dispositivo some
        quadros.append(tuple(self._linhas[y] for y in sorted(self._linhas)))

    def poweroff(self):
        pass

    def contrast(self, c):
        pass
