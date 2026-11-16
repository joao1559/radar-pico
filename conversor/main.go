// Conversor: radares.csv (murkiriel/pardal) -> radares.bin compacto para o Pico W.
//
// Formato do .bin (little-endian), versão 1:
//
//	Cabeçalho (16 bytes): "PRDL" | u16 versão | u16 divisões por grau | u32 nCélulas | u32 nRadares
//	Índice   (10 bytes x nCélulas, ordenado por célula): u32 célula | u32 primeiroRadar | u16 quantidade
//	Radares  (16 bytes x nRadares, agrupados por célula):
//	         i32 lat*1e6 | i32 lng*1e6 | u8 limite (0 = desconhecido) | u8 tipo (0 fixo, 1 trecho, 2 semáforo)
//	         u16 direção (0-359, 0xFFFF = ambos) | i16 dLatFim*1e4 | i16 dLngFim*1e4 (só trecho; 0,0 = sem fim)
//
// Célula = floor((lat+90)*div)*(360*div) + floor((lng+180)*div); div = 10 -> células de 0,1°.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/csv"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
)

const (
	versao     = 1
	divisoes   = 10
	semDirecao = 0xFFFF
)

var tipos = map[string]uint8{"FIXED": 0, "SECTION": 1, "RED_LIGHT": 2}

type Radar struct {
	Lat, Lng   int32
	Limite     uint8
	Tipo       uint8
	Direcao    uint16
	DLat, DLng int16
	Celula     uint32
}

func main() {
	entrada := flag.String("in", "https://raw.githubusercontent.com/murkiriel/pardal/main/brasil/radares.csv",
		"caminho ou URL do radares.csv")
	saida := flag.String("out", "radares.bin", "arquivo de saída")
	bbox := flag.String("bbox", "", "filtro opcional: minLat,minLng,maxLat,maxLng")
	semSemaforo := flag.Bool("sem-semaforo", false, "ignora radares de semáforo (RED_LIGHT)")
	flag.Parse()

	r, err := abrir(*entrada)
	if err != nil {
		log.Fatal(err)
	}
	defer r.Close()

	var filtro *[4]float64
	if *bbox != "" {
		f, err := lerBBox(*bbox)
		if err != nil {
			log.Fatal(err)
		}
		filtro = &f
	}

	radares, ignorados, err := lerCSV(r, filtro, *semSemaforo)
	if err != nil {
		log.Fatal(err)
	}

	var buf bytes.Buffer
	nCelulas := codificar(&buf, radares)
	if err := os.WriteFile(*saida, buf.Bytes(), 0o644); err != nil {
		log.Fatal(err)
	}
	soma := sha256.Sum256(buf.Bytes())
	// versao.txt: o Pico compara com o que já tem para saber se precisa baixar.
	if err := os.WriteFile(*saida+".versao", []byte(hex.EncodeToString(soma[:])+"\n"), 0o644); err != nil {
		log.Fatal(err)
	}
	log.Printf("%d radares em %d células (%d ignorados) -> %s, %d bytes",
		len(radares), nCelulas, ignorados, *saida, buf.Len())
}

func abrir(caminho string) (io.ReadCloser, error) {
	if strings.HasPrefix(caminho, "http://") || strings.HasPrefix(caminho, "https://") {
		resp, err := http.Get(caminho)
		if err != nil {
			return nil, err
		}
		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			return nil, fmt.Errorf("GET %s: %s", caminho, resp.Status)
		}
		return resp.Body, nil
	}
	return os.Open(caminho)
}

func lerBBox(s string) ([4]float64, error) {
	var b [4]float64
	partes := strings.Split(s, ",")
	if len(partes) != 4 {
		return b, errors.New("bbox precisa de 4 valores: minLat,minLng,maxLat,maxLng")
	}
	for i, p := range partes {
		v, err := strconv.ParseFloat(strings.TrimSpace(p), 64)
		if err != nil {
			return b, fmt.Errorf("bbox: %w", err)
		}
		b[i] = v
	}
	return b, nil
}

func lerCSV(r io.Reader, bbox *[4]float64, semSemaforo bool) ([]Radar, int, error) {
	cr := csv.NewReader(r)
	cab, err := cr.Read()
	if err != nil {
		return nil, 0, fmt.Errorf("lendo cabeçalho: %w", err)
	}
	col := map[string]int{}
	for i, c := range cab {
		col[strings.TrimSpace(c)] = i
	}
	for _, obrig := range []string{"lat", "lng", "kind", "limit_kmh", "active", "end_lat", "end_lng", "direction_deg"} {
		if _, ok := col[obrig]; !ok {
			return nil, 0, fmt.Errorf("coluna %q não encontrada", obrig)
		}
	}

	vistos := map[[4]int64]bool{}
	var out []Radar
	ignorados := 0
	for {
		linha, err := cr.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, 0, err
		}
		campo := func(n string) string { return strings.TrimSpace(linha[col[n]]) }

		if campo("active") != "1" {
			ignorados++
			continue
		}
		tipo, ok := tipos[campo("kind")]
		if !ok || (semSemaforo && tipo == 2) {
			ignorados++
			continue
		}
		lat, err1 := strconv.ParseFloat(campo("lat"), 64)
		lng, err2 := strconv.ParseFloat(campo("lng"), 64)
		if err1 != nil || err2 != nil || lat < -90 || lat > 90 || lng < -180 || lng > 180 {
			ignorados++
			continue
		}
		if bbox != nil && (lat < bbox[0] || lng < bbox[1] || lat > bbox[2] || lng > bbox[3]) {
			ignorados++
			continue
		}

		rd := Radar{
			Lat:     int32(math.Round(lat * 1e6)),
			Lng:     int32(math.Round(lng * 1e6)),
			Tipo:    tipo,
			Direcao: semDirecao,
			Celula:  celula(lat, lng),
		}
		if v, err := strconv.Atoi(campo("limit_kmh")); err == nil && v > 0 && v < 255 {
			rd.Limite = uint8(v)
		}
		if v, err := strconv.Atoi(campo("direction_deg")); err == nil && v >= 0 && v < 360 {
			rd.Direcao = uint16(v)
		}
		if tipo == 1 {
			eLat, e1 := strconv.ParseFloat(campo("end_lat"), 64)
			eLng, e2 := strconv.ParseFloat(campo("end_lng"), 64)
			if e1 == nil && e2 == nil {
				dLat := math.Round((eLat - lat) * 1e4)
				dLng := math.Round((eLng - lng) * 1e4)
				if math.Abs(dLat) <= math.MaxInt16 && math.Abs(dLng) <= math.MaxInt16 {
					rd.DLat, rd.DLng = int16(dLat), int16(dLng)
				}
			}
		}

		chave := [4]int64{int64(rd.Lat), int64(rd.Lng), int64(rd.Tipo), int64(rd.Direcao)}
		if vistos[chave] {
			ignorados++
			continue
		}
		vistos[chave] = true
		out = append(out, rd)
	}
	return out, ignorados, nil
}

func celula(lat, lng float64) uint32 {
	cLat := uint32(math.Floor((lat + 90) * divisoes))
	cLng := uint32(math.Floor((lng + 180) * divisoes))
	return cLat*360*divisoes + cLng
}

// codificar escreve o .bin e devolve o número de células.
func codificar(w *bytes.Buffer, radares []Radar) int {
	sort.Slice(radares, func(i, j int) bool {
		if radares[i].Celula != radares[j].Celula {
			return radares[i].Celula < radares[j].Celula
		}
		if radares[i].Lat != radares[j].Lat {
			return radares[i].Lat < radares[j].Lat
		}
		return radares[i].Lng < radares[j].Lng
	})

	type entrada struct {
		Celula, Primeiro uint32
		Qtd              uint16
	}
	var indice []entrada
	for i, rd := range radares {
		n := len(indice)
		if n > 0 && indice[n-1].Celula == rd.Celula && indice[n-1].Qtd < math.MaxUint16 {
			indice[n-1].Qtd++
			continue
		}
		indice = append(indice, entrada{rd.Celula, uint32(i), 1})
	}

	le := binary.LittleEndian
	w.WriteString("PRDL")
	binary.Write(w, le, uint16(versao))
	binary.Write(w, le, uint16(divisoes))
	binary.Write(w, le, uint32(len(indice)))
	binary.Write(w, le, uint32(len(radares)))
	for _, e := range indice {
		binary.Write(w, le, e.Celula)
		binary.Write(w, le, e.Primeiro)
		binary.Write(w, le, e.Qtd)
	}
	for _, rd := range radares {
		binary.Write(w, le, rd.Lat)
		binary.Write(w, le, rd.Lng)
		binary.Write(w, le, rd.Limite)
		binary.Write(w, le, rd.Tipo)
		binary.Write(w, le, rd.Direcao)
		binary.Write(w, le, rd.DLat)
		binary.Write(w, le, rd.DLng)
	}
	return len(indice)
}
