# radar-pico

Alerta sonoro de radares no carro com Raspberry Pi Pico W + GPS, usando a base aberta
[murkiriel/pardal](https://github.com/murkiriel/pardal) (dados ODbL — credite o OpenStreetMap
e as fontes; não é fonte oficial).

```
conversor/   Go: radares.csv -> radares.bin (16 B por radar, indexado em células de 0,1°)
firmware/    MicroPython para o Pico W
sim/         simulador no PC (testa a mesma lógica do firmware)
.github/     Action semanal que gera e publica o radares.bin na branch "dados"
```

## Hardware

| Peça | Ligação |
|---|---|
| GPS NEO-6M ou NEO-M8N | VCC 3V3 (ou 5V, conforme o módulo) · GND · TX do GPS → **GP1** · RX do GPS → GP0 |
| Buzzer **passivo** | + → **GP15** (de preferência via transistor NPN + resistor 1 kΩ) · − → GND |
| OLED SSD1306 128×64 (opcional) | SDA → **GP4** · SCL → **GP5** · 3V3 · GND |
| Alimentação | USB do carro ou buck 12 V → 5 V no VSYS |

A antena do GPS precisa “ver o céu”: perto do para-brisa, longe de película metalizada.

## Uso

1. **Gerar a base** (precisa de Go):
   ```bash
   cd conversor
   go run .                                   # Brasil inteiro (~350 KB, cabe no Pico W)
   go run . -in caminho/estados/SP/radares.csv  # ou só um estado
   go run . -bbox -21.0,-48.0,-20.0,-47.0     # ou só uma região
   ```
2. **Testar no PC**:
   ```bash
   python3 sim/simula.py teste                 # passa por 300 radares aleatórios, nos dois sentidos
   python3 sim/simula.py gpx meu_trajeto.gpx   # reproduz um trajeto gravado (1 ponto/s)
   ```
3. **Gravar no Pico W**: instale o firmware MicroPython do Pico W, depois
   ```bash
   pip install mpremote
   mpremote mip install ssd1306                # só se usar o OLED
   mpremote cp firmware/*.py :
   mpremote cp conversor/radares.bin :
   ```
   Edite `firmware/config.py` (Wi-Fi, URL, pinos) antes de copiar.
4. **Atualização automática**: faça push deste repositório no seu GitHub. O Action roda toda segunda
   (ou manualmente em *Actions → Gera radares.bin → Run workflow*) e publica na branch `dados`.
   Aponte `URL_BASE` do `config.py` para
   `https://raw.githubusercontent.com/<você>/<repo>/dados/radares.bin`. No boot, se o Pico achar o
   Wi-Fi (garagem ou hotspot do celular), compara a versão e baixa só se mudou.

## Como o alerta decide

A cada fix do GPS (sentença RMC):

- lê só as células de 0,1° a menos de 1,5 km (fica no máx. ~12 KB em RAM, mesmo no centro de SP);
- ignora radar cujo sentido (`direction_deg`) difere do seu rumo em mais de 45°;
- exige que o radar esteja num cone de ±30° à frente;
- distância de aviso = 15 s na velocidade atual (mín. 300 m, máx. 1,2 km);
- **1 bipe** no aviso, **2 bipes** a ~6 s / 120 m, **bipe agudo repetido** se estiver acima do limite;
- radares de várias faixas a menos de 60 m contam como um só;
- radar de trecho: depois do início, calcula a velocidade média até o ponto final;
- abaixo de 10 km/h não procura radar novo (o rumo do GPS fica instável parado).

Tudo isso está em `firmware/radar.py` (classe `Alertador`), com as constantes no topo da classe.

## Legal

Alertar posição de radar a partir de base de dados (como o Waze) é permitido. Já **detector de
radar** (que capta o sinal do equipamento) é proibido pelo CTB — este projeto não faz isso.
