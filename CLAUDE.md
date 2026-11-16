# Contexto do projeto (para o Claude Code)

Projeto pessoal do João: alerta sonoro de radares no carro com **Raspberry Pi Pico W + GPS**, usando a
base aberta [murkiriel/pardal](https://github.com/murkiriel/pardal). Responder em português.
O João é dev backend Go; prefere Go no ferramental e MicroPython no firmware.

## Estado atual

- **Feito e testado no PC**: conversor Go, lógica de alerta (`firmware/radar.py`), parser NMEA, simulador.
- **Escrito mas NUNCA rodado em hardware real**: `firmware/main.py` (UART/PWM/OLED) e
  `firmware/atualiza.py` (Wi-Fi + download). O primeiro teste na placa é a próxima etapa.
- GitHub Action (`.github/workflows/base.yml`) escrito, ainda não rodou. `config.py` tem placeholders
  (Wi-Fi e `URL_BASE` com `SEU_USUARIO`).

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
  células a < 1,5 km da posição e guarda bytes crus (pior caso medido: 799 radares ≈ 12 KB).
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
mpremote cp firmware/*.py : && mpremote cp sim/radares.bin :
```

Último resultado do `simula.py teste`: 300/300 alertas no sentido certo, 0 no sentido errado;
1º aviso 278 m @40, 276 m @60, 300 m @80, 413 m @110 km/h.

## Hardware

GPS (NEO-6M/M8N, 9600 baud) TX → GP1, RX → GP0 · buzzer **passivo** GP15 (PWM) ·
OLED SSD1306 opcional SDA GP4 / SCL GP5 · alimentação USB do carro ou buck 12→5 V no VSYS.

## Pontos a verificar na placa / ideias pendentes

- `requests` do MicroPython: confirmar `r.raw.read()` em HTTPS e o tratamento de redirect.
- Bipe é bloqueante (até ~280 ms); UART com `rxbuf=2048` para não perder NMEA. Se der problema, migrar
  para `uasyncio` ou timer.
- Possível: configurar o GPS para 5 Hz via UBX (M8N), modo silencioso, botão de mudo.
- Licença dos dados: ODbL (creditar OSM e fontes). Detector de radar por RF é proibido; este projeto só usa base.
