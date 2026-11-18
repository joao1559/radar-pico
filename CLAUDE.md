# Contexto do projeto (para o Claude Code)

Projeto pessoal do João: alerta sonoro de radares no carro com **Raspberry Pi Pico W + GPS**, usando a
base aberta [murkiriel/pardal](https://github.com/murkiriel/pardal). Responder em português.
O João é dev backend Go; prefere Go no ferramental e MicroPython no firmware.

## Estado atual

- **Feito e testado no PC**: conversor Go, lógica de alerta (`firmware/radar.py`), parser NMEA, simulador.
- **Escrito mas NUNCA rodado em hardware real**: `firmware/main.py` (UART/PWM/OLED) e
  `firmware/atualiza.py` (Wi-Fi + download). O João ainda não tem a placa/componentes (2026-11-16).
- `main.py` já roda inteiro no PC com hardware falso (`sim/fake/`: machine, ssd1306, network, requests +
  relógio virtual) via `simula.py placa`: 6 cenários OK (achou e corrigiu o LED "piscando" a ~10 Hz).
  Não mede RAM nem CPU do Pico. `atualiza.py` só foi exercitado no caminho "sem Wi-Fi".
- **Pico W real (MicroPython 1.28, RPI_PICO_W), sem módulos, 2026-11-16**: firmware + base copiados
  (700 KB livres antes); `main.py` boota até "SEM GPS". `mpremote run sim/bench_pico.py` mede o Alertador:
  Brasília mediana 1 ms / p95 158 ms / máx 743 ms (troca de célula); SP centro ~40 ms; isolado 2 ms;
  `gps.ler_rmc` 4 ms. A extensão MicroPico do VS Code segura a COM5: desconectar antes do mpremote.
- **Wi-Fi/atualização testados no Pico real** (`python3 sim/teste_wifi.py <cenario>`: https, nova, igual,
  corrompida, cortada, travada; o PC serve a base na porta 8765). HTTPS + `r.raw.read()` OK; o `requests`
  1.28 já segue redirect sozinho. Flash com base tem só ~324 KB livres < 343 KB, então a base velha é
  apagada antes do download: por isso `atualiza.py` tem timeout de 15 s, 3 tentativas, e baixa se não houver
  `radares.bin` mesmo com a versão em dia. Não reverter.
- Fragmentação (`mpremote run sim/frag_pico.py`, 20 min, 898 trocas de cache em Brasília/SP/Rio/BH):
  0 MemoryError, mas o maior bloco livre caiu a 30 KB (precisa de ~21 KB em Brasília). Margem pequena:
  candidato a pré-alocar um buffer fixo e usar `readinto`.
- Credenciais do Wi-Fi ficam em `firmware/segredos.py` (gitignored, importado pelo `config.py`); nunca
  colocar senha no `config.py`.
- **Módulos reais (2026-11-17)**: OLED responde em 0x3C e mostra texto. O "NEO-6M" é na verdade um chip
  compatível multi-GNSS (AT6558/ATGM336H: `$GNRMC`, `$BDGSA`, `$GNZDA`, `$GPTXT ANTENNA OK`) → UBX/5 Hz
  não se aplica (usa comandos `$PCAS`). Partida a frio pela janela: fix em 285 s, depois estável 30 min com
  8–9 satélites, HDOP 1,2. `sim/gps_pico.py` monitora fix (com `SOZINHO = True` roda como main.py sem PC e
  grava `gps_log.txt`). Buzzer ainda não chegou. `main.py` agora mostra "Livre | X km/h" a cada fix.
- Repo `joao1559/radar-pico`; a Action rodou (manual, 2026-11-16) e publicou a branch `dados`. O Pico baixou
  a base real do GitHub por HTTPS (343 KB em ~14 s) e reconhece "base em dia".

## Decisões de arquitetura (e por quê)

- **Pré-processar fora do carro.** O CSV do pardal (`lat,lng,kind,limit_kmh,source,active,end_lat,end_lng,direction_deg`)
  vira um binário compacto. Formato documentado no topo de `conversor/main.go`:
  cabeçalho 16 B ("PRDL", versão 1, div=10, nCélulas, nRadares) + índice 10 B/célula + 16 B/radar.
  Células de 0,1° ordenadas → busca binária no arquivo, sem carregar tudo na RAM.
- Só radares `active=1`. `direction_deg` vazio = ambos os sentidos (0xFFFF). Trecho (`SECTION`) guarda o
  fim como delta int16 em 1e-4°.
- **Tamanho** (base de 2026-11-15): Brasil 19.874 radares → 343 KB (cabe na flash do Pico W, ~848 KB livres);
  SP 5.166 → 88 KB.
- **RAM**: no centro de SP, 3×3 células = 1.813 radares (estourava a RAM). Solução: `Base.proximos()` só lê
  células a < 1,5 km da posição e guarda bytes crus. Pior caso na base 2026-11-15: centro de Brasília,
  1.326 radares → 24 KB retidos no Pico real (de ~191 KB livres).
  `Radar` só é instanciado para o radar escolhido. Não reverter isso.
- **Grupos**: radares por faixa ficam ~20 m um do outro; ao passar por um, todos a < 60 m (`RAIO_GRUPO`)
  são marcados como passados.
- **Regras do alerta** (`Alertador`): sentido ±45° do rumo; radar num cone ±30° à frente (exceto < 30 m);
  aviso a 15 s (300–1200 m); "perto" a 6 s / ≥120 m; excesso se vel > limite + tolerância;
  não procura radar novo abaixo de 10 km/h; esquece radar passado após 180 s; radar de trecho
  integra distância/tempo e alerta pela média.
- `radar.py` só usa `math`/`struct` para rodar igual em MicroPython e CPython (sem `__slots__`,
  sem f-strings complexas, sem libs externas).
- Atualização: Action semanal (segunda, depois do update de domingo do pardal) publica `radares.bin` +
  `radares.bin.versao` (sha256) na branch `dados`; no boot o Pico compara a versão e só baixa se mudou;
  apaga a base velha antes se a flash não comportar as duas; desliga o Wi-Fi depois.

## Comandos

```bash
cd conversor && go test ./... && go run . -in <csv ou URL> -out ../sim/radares.bin
python3 sim/simula.py teste            # 300 passagens nos dois sentidos; exit 1 se falhar
python3 sim/simula.py gpx trajeto.gpx  # reproduz trajeto gravado (assume 1 ponto/s)
python3 sim/simula.py placa [x.gpx] [-v]  # roda firmware/main.py inteiro com hardware falso; exit 1 se falhar
mpremote cp firmware/*.py : && mpremote cp sim/radares.bin :
```

Nesta máquina (Windows) `python3` do PATH é o atalho da Store: usar `~/.local/bin/python3.14.exe` (uv),
com `PYTHONIOENCODING=utf-8`. `sim/radares.bin` não é versionado: gerar com o conversor.

Último resultado do `simula.py teste`: 300/300 alertas no sentido certo, 0 no sentido errado;
1º aviso 278 m @40, 276 m @60, 300 m @80, 413 m @110 km/h.

## Hardware

GPS (NEO-6M/M8N, 9600 baud) TX → GP1, RX → GP0 · buzzer **passivo** GP15 (PWM) ·
OLED SSD1306 (faz parte do projeto) SDA GP4 / SCL GP5 — driver via `mpremote mip install ssd1306` (já na placa, ~3 KB RAM); se a tela falhar no `show()`, o `main.py` segue só com som · alimentação USB do carro ou buck 12→5 V no VSYS.

## Caixa 3D

`caixa/caixa.scad` (OpenSCAD, paramétrico): partes caixa / tampa / teste_oled / teste_buzzer. OLED na frente,
USB do Pico na lateral direita, antena do GPS colada na tampa acima do GPS (cabinho curto), buzzer 12×9,5 mm
num tubo na tampa. Fios soldados direto (2026-11-18): `pico_alt = 4`, `int_z = 30` (17/32 se voltar a usar dupont). OLED medido (placa 25×27, furos 21×24, área acesa a 5 mm do topo; montar com pinos para cima); antena 25×25 confere; placa do GPS 35×30 medida. Imprimir em PETG/ASA.
Fixação no carro ainda indefinida (fundo reto). OpenSCAD 2021.01 instalado (`"/c/Program Files/OpenSCAD/openscad.com" -o caixa/stl/<parte>.stl -D parte=\"<parte>\" caixa/caixa.scad`); STLs em `caixa/stl/`, todas as peças 1 corpo só e sem colisão com os componentes.

## Pontos a verificar na placa / ideias pendentes

- Bipe é bloqueante (até ~280 ms); UART com `rxbuf=2048` para não perder NMEA. Se der problema, migrar
  para `uasyncio` ou timer.
- Possível: GPS a 5 Hz (no AT6558 via `$PCAS02`, não UBX), modo silencioso, botão de mudo.
- Licença dos dados: ODbL (creditar OSM e fontes). Detector de radar por RF é proibido; este projeto só usa base.
