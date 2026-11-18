// Caixa do Radar Pico (Pico W + GPS NEO-6M + OLED 0.96" + buzzer 12 mm) — OpenSCAD 2021+
//
// Como usar: abra no OpenSCAD, escolha `parte` (ou use Window > Customizer), F6 para renderizar,
// File > Export > STL. Imprima "caixa" e "tampa" separadas, sem suporte.
// MATERIAL: PETG ou ASA. PLA amolece a ~55 °C e deforma no painel do carro ao sol.
//
// As medidas do OLED e do GPS variam entre fabricantes: MEÇA a sua peça e ajuste aqui.
// Antes da caixa inteira, imprima "teste_oled" e "teste_buzzer" (10–15 min cada) para conferir.
//
// Coordenadas internas: x = largura (esquerda→direita, olhando a frente), y = profundidade
// (frente→fundo), z = altura a partir do piso interno. A frente (y=0) tem o OLED; o USB sai à direita.

parte = "tudo"; // [tudo, caixa, tampa, teste_oled, teste_buzzer]

/* [Caixa] */
int_x = 100;        // medidas internas (mm)
int_y = 58;
int_z = 30;         // quem limita é o OLED de pé na frente (27,8 mm)
parede = 2.4;
fundo = 2.0;
tampa_esp = 2.0;
raio_canto = 3;
folga = 0.3;        // folga de encaixe da tampa
poste = 7;          // postes dos cantos, onde entram os parafusos da tampa
furo_piloto = 2.5;  // parafuso M3 autoatarraxante (ou M3 x 10 de madeira)
furo_tampa = 3.4;
cabeca_paraf = 6.2; // escareado M3

/* [Pico W] */
pico_l = 51;
pico_w = 21;
pico_esp = 1;
// 4 mm: fios soldados direto na placa (sem barra de pinos). Use 17 se usar barra de pinos + jumper dupont.
pico_alt = 4;
usb_largura = 13;   // furo para o plug do cabo (a capa plástica do plug é maior que o conector)
usb_altura = 9;

/* [OLED 0.96" I2C SSD1306] */
oled_pcb = [27.3, 27.8];    // largura x altura da placa
oled_furos = [23.0, 23.5];  // distância entre os centros dos furos (meça!)
oled_furo_d = 2.0;          // diâmetro dos furos da placa
oled_janela = [24, 13];     // abertura da tela (área ativa ~21,7 x 10,9)
oled_janela_dz = 0;         // + sobe a janela, - desce (se a tela não ficar centrada)
oled_x = 25;                // centro do OLED, medido da parede esquerda interna
oled_recuo = 2.6;           // distância parede→placa: o vidro da tela deve encostar na parede

/* [GPS NEO-6M] */
gps_pcb = [35, 25];         // placa do módulo (a antena fica na tampa)
ant = 25.0;                 // antena cerâmica quadrada
ant_tol = 0.8;
ant_parede = 1.6;
ant_alt = 3;                // altura da moldura que segura a antena

/* [Buzzer passivo 12 mm] */
buz_d = 12;
buz_alt = 9.5;
buz_x = 78;
buz_y = 13;

/* [Escondido] */
$fn = 48;
ext = [int_x + 2 * parede, int_y + 2 * parede, int_z + fundo];
pico_furos = [[2, 4.8], [2, 16.2], [49, 4.8], [49, 16.2]];   // datasheet do Pico
pico_x0 = int_x - pico_l - 1;                  // 1 mm da parede direita (USB)
pico_y0 = int_y - poste - pico_w - 1;          // atrás, livre dos postes
oled_z = int_z / 2;
gps_x0 = 2;
gps_y0 = int_y - poste - gps_pcb[1] - 2;
ant_x = gps_x0 + gps_pcb[0] / 2 + 1.5;         // logo acima do GPS: o cabinho da antena é curto
ant_y = gps_y0 + gps_pcb[1] / 2;

function centros_postes() = [[poste / 2, poste / 2], [int_x - poste / 2, poste / 2],
                             [poste / 2, int_y - poste / 2], [int_x - poste / 2, int_y - poste / 2]];

module arred_cubo(s, r) {
    hull() for (x = [r, s[0] - r], y = [r, s[1] - r]) translate([x, y, 0]) cylinder(r = r, h = s[2]);
}

module interno() { translate([parede, parede, fundo]) children(); }

module janela_oled() {
    w = oled_janela[0]; h = oled_janela[1]; c = 1.5;  // chanfro para ver a tela de lado
    hull() {
        translate([-w / 2, -0.6, -h / 2]) cube([w, 0.7, h]);
        translate([-w / 2 - c, -parede - 0.1, -h / 2 - c]) cube([w + 2 * c, 0.1, h + 2 * c]);
    }
}

module cercado_gps() {
    t = 1.2; f = 0.6; a = 3.5;
    translate([gps_x0 - f - t, gps_y0 - f - t, 0]) difference() {
        cube([gps_pcb[0] + 2 * (f + t), gps_pcb[1] + 2 * (f + t), a]);
        translate([t, t, -1]) cube([gps_pcb[0] + 2 * f, gps_pcb[1] + 2 * f, a + 2]);
        // lado direito aberto: se os pinos do GPS saírem de lado, não batem no cercado
        translate([gps_pcb[0] + f + t - 0.1, t + 4, -1]) cube([t + 1, gps_pcb[1] + 2 * f - 8, a + 2]);
    }
}

module caixa() {
    difference() {
        union() {
            difference() {
                arred_cubo(ext, raio_canto);
                translate([parede, parede, fundo]) cube([int_x, int_y, int_z + 1]);
            }
            interno() {
                for (c = centros_postes()) translate([c[0] - poste / 2, c[1] - poste / 2, -0.5]) cube([poste, poste, int_z + 0.5]);
                for (f = pico_furos) translate([pico_x0 + f[0], pico_y0 + f[1], -0.5]) cylinder(d = 5, h = pico_alt + 0.5);
                translate([0, 0, -0.5]) cercado_gps();
                // OLED: espaçador + pino que passa no furo da placa (prenda com uma gota de cola quente)
                for (sx = [-1, 1], sz = [-1, 1])
                    translate([oled_x + sx * oled_furos[0] / 2, 0, oled_z + sz * oled_furos[1] / 2])
                        rotate([-90, 0, 0]) translate([0, 0, -0.5]) {  // 0,5 mm dentro da parede: funde com ela
                            cylinder(d = 4.0, h = oled_recuo + 0.5);  // < 4,2: não pode encostar no vidro
                            cylinder(d = oled_furo_d - 0.3, h = oled_recuo + 3);
                        }
            }
        }
        interno() {
            for (c = centros_postes()) translate([c[0], c[1], int_z - 12]) cylinder(d = furo_piloto, h = 13);
            for (f = pico_furos) let (prof = min(6, pico_alt + fundo - 0.8))  // nunca fura o fundo da caixa
                translate([pico_x0 + f[0], pico_y0 + f[1], pico_alt - prof]) cylinder(d = 1.8, h = prof + 1);
            translate([oled_x, 0, oled_z + oled_janela_dz]) janela_oled();
            // USB do Pico (o conector fica em cima da placa)
            translate([int_x - 1, pico_y0 + pico_w / 2, pico_alt + pico_esp + 1.5]) rotate([0, 90, 0])
                linear_extrude(parede + 2) offset(r = 2) square([usb_altura - 4, usb_largura - 4], center = true);
            // ventilação no fundo
            for (i = [0:4]) translate([int_x / 2 - 20 + i * 10 - 1, int_y - 1, 8]) cube([2, parede + 2, 14]);
        }
    }
}

module tampa_montada() {  // na posição final, em coordenadas da caixa
    difference() {
        union() {
            translate([0, 0, fundo + int_z]) arred_cubo([ext[0], ext[1], tampa_esp], raio_canto);
            interno() {
                // moldura da antena (cerâmica virada para cima, cabo para baixo)
                s = ant + ant_tol + 2 * ant_parede;
                translate([ant_x, ant_y, int_z - ant_alt]) difference() {
                    translate([-s / 2, -s / 2, 0]) cube([s, s, ant_alt + 0.01]);
                    translate([-(ant + ant_tol) / 2, -(ant + ant_tol) / 2, -1]) cube([ant + ant_tol, ant + ant_tol, ant_alt + 2]);
                    translate([s / 2 - ant_parede - 1, -5, -1]) cube([ant_parede + 2, 10, ant_alt + 2]);  // saída do cabo
                }
                // tubo do buzzer (entra apertado; um pingo de cola quente segura de vez)
                translate([buz_x, buz_y, int_z - (buz_alt - 1.5)]) difference() {
                    cylinder(d = buz_d + 0.4 + 3.2, h = buz_alt - 1.5 + 0.01);
                    translate([0, 0, -1]) cylinder(d = buz_d + 0.4, h = buz_alt + 2);
                }
                // abas que centralizam a tampa
                translate([int_x / 2 - 8, folga, int_z - 3]) cube([16, 1.2, 3]);
                translate([int_x / 2 - 8, int_y - folga - 1.2, int_z - 3]) cube([16, 1.2, 3]);
                translate([folga, int_y / 2 - 8, int_z - 3]) cube([1.2, 16, 3]);
                translate([int_x - folga - 1.2, int_y / 2 - 8, int_z - 3]) cube([1.2, 16, 3]);
            }
        }
        interno() {
            for (c = centros_postes()) translate([c[0], c[1], int_z - 1]) {
                cylinder(d = furo_tampa, h = tampa_esp + 2);
                translate([0, 0, 1 + tampa_esp - 1.7]) cylinder(d1 = furo_tampa, d2 = cabeca_paraf, h = 1.71);
            }
            translate([buz_x, buz_y, int_z - 1])
                for (i = [-2:2], j = [-2:2]) if (i * i + j * j <= 5)
                    translate([i * 2.2, j * 2.2, 0]) cylinder(d = 1.4, h = tampa_esp + 2, $fn = 16);
        }
    }
}

module tampa_impressao() {  // de cabeça para baixo: as peças internas ficam para cima, sem suporte
    translate([0, ext[1], 0]) rotate([180, 0, 0]) translate([0, 0, -(fundo + int_z + tampa_esp)]) tampa_montada();
}

module fantasmas() {  // só para visualizar no modo "tudo" (não vai para o STL)
    interno() {
        color("green", 0.5) translate([pico_x0, pico_y0, pico_alt]) cube([pico_l, pico_w, pico_esp]);
        color("silver", 0.6) translate([int_x - 1 - 5.5, pico_y0 + pico_w / 2 - 4, pico_alt + pico_esp]) cube([5.5, 8, 3]);
        color("blue", 0.5) translate([gps_x0, gps_y0, 0.5]) cube([gps_pcb[0], gps_pcb[1], 1.6]);
        color("tan", 0.6) translate([ant_x - ant / 2, ant_y - ant / 2, int_z - 4]) cube([ant, ant, 4]);
        color("navy", 0.5) translate([oled_x - oled_pcb[0] / 2, oled_recuo, oled_z - oled_pcb[1] / 2]) cube([oled_pcb[0], 1.6, oled_pcb[1]]);
        color("black", 0.6) translate([buz_x, buz_y, int_z - buz_alt]) cylinder(d = buz_d, h = buz_alt);
    }
}

if (parte == "caixa") caixa();
else if (parte == "tampa") tampa_impressao();
else if (parte == "teste_oled")
    intersection() { caixa(); translate([parede + oled_x - 20, 0, 0]) cube([40, parede + oled_recuo + 4, ext[2]]); }
else if (parte == "teste_buzzer")
    intersection() { tampa_impressao(); translate([parede + buz_x - 12, ext[1] - parede - buz_y - 12, 0]) cube([24, 24, 20]); }
else if (parte == "tudo") {
    caixa();
    %fantasmas();
    translate([0, 0, 30]) color("lightgray", 0.6) tampa_montada();
}
