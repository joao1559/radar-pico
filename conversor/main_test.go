package main

import (
	"bytes"
	"encoding/binary"
	"strings"
	"testing"
)

const csvTeste = `lat,lng,kind,limit_kmh,source,active,end_lat,end_lng,direction_deg
-20.538000,-47.400000,FIXED,60,OSM,1,,,90
-20.538000,-47.400000,FIXED,60,ANTT,1,,,90
-20.540000,-47.401000,SECTION,80,DNIT,1,-20.560000,-47.420000,
-20.541000,-47.402000,FIXED,40,OSM,0,,,
-20.542000,-47.403000,RED_LIGHT,,OSM,1,,,
`

func TestLerCSV(t *testing.T) {
	rs, ign, err := lerCSV(strings.NewReader(csvTeste), nil, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(rs) != 3 || ign != 2 { // 1 duplicado + 1 inativo
		t.Fatalf("esperava 3 radares e 2 ignorados, veio %d e %d", len(rs), ign)
	}
	if rs[0].Direcao != 90 || rs[0].Limite != 60 {
		t.Errorf("fixo: %+v", rs[0])
	}
	if rs[1].Direcao != semDirecao || rs[1].DLat != -200 || rs[1].DLng != -190 {
		t.Errorf("trecho: %+v", rs[1])
	}
}

func TestCodificar(t *testing.T) {
	rs, _, _ := lerCSV(strings.NewReader(csvTeste), nil, false)
	var buf bytes.Buffer
	nc := codificar(&buf, rs)
	b := buf.Bytes()
	if string(b[:4]) != "PRDL" {
		t.Fatal("magic errado")
	}
	nCel := binary.LittleEndian.Uint32(b[8:])
	nRad := binary.LittleEndian.Uint32(b[12:])
	if int(nCel) != nc || nRad != 3 {
		t.Fatalf("cabeçalho: %d células, %d radares", nCel, nRad)
	}
	if want := 16 + 10*int(nCel) + 16*int(nRad); len(b) != want {
		t.Fatalf("tamanho %d, esperado %d", len(b), want)
	}
}
