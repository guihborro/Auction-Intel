"""
build_sql_coords.py — Coordenada por QUADRA via GeoSampa (WFS), casando pelo SQL.

Descobertas que moldam este script:
  * O SQL do ITBI é canônico com 11 dígitos: SSS.QQQ.LLLL-D (zfill para 11).
  * O filtro WFS `cd_setor_fiscal` é STRING zero-paddada ('010'), não inteiro.
  * Apartamentos são UNIDADES de condomínio; a camada `lote_cidadao` é a nível
    de LOTE (terreno do prédio), então o casamento por lote falha. Mas o
    casamento por QUADRA (setor+quadra) cobre ~96%. Usamos o centroide da quadra
    (quarteirão, ~precisão de bairro de rua) como coordenada do imóvel.

Saída: datasets/quadra_coords.csv  (quadra6, latitude, longitude) — resumível.
"""
import os
import time
from collections import defaultdict

import pandas as pd
import requests
from shapely.geometry import shape

ITBI = "datasets/itbi_2024_apartments.csv"
OUT = "datasets/quadra_coords.csv"
WFS = "http://wms.geosampa.prefeitura.sp.gov.br/geoserver/ows"
H = {"User-Agent": "Mozilla/5.0"}


def fetch_setor(setor):
    """Retorna {quadra6: (lat, lon)} — centroide médio dos lotes de cada quadra."""
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "geoportal:lote_cidadao", "outputFormat": "application/json",
        "srsName": "EPSG:4326", "count": 20000,
        "CQL_FILTER": f"cd_setor_fiscal='{setor}'",
        "propertyName": "cd_setor_fiscal,cd_quadra_fiscal,ge_poligono",
    }
    r = requests.get(WFS, params=params, headers=H, timeout=180)
    r.raise_for_status()
    agg = defaultdict(lambda: [0.0, 0.0, 0])
    for feat in r.json().get("features", []):
        p = feat["properties"]
        geom = feat.get("geometry")
        q = p.get("cd_quadra_fiscal")
        if not geom or q in (None, "None"):
            continue
        try:
            key = f"{setor}{int(q):03d}"
        except (TypeError, ValueError):
            continue
        c = shape(geom).centroid
        a = agg[key]
        a[0] += c.y; a[1] += c.x; a[2] += 1
    return {k: (round(v[0] / v[2], 7), round(v[1] / v[2], 7)) for k, v in agg.items() if v[2]}


def main():
    itbi = pd.read_csv(ITBI)
    sql11 = itbi["sql"].astype("Int64").astype(str).str.zfill(11)
    needed = set(sql11.str[:6])                      # quadras (setor+quadra) do ITBI
    setores = sorted(sql11.str[:3].unique())         # strings zero-paddadas
    print(f"{len(needed)} quadras necessárias | {len(setores)} setores")

    done = set()
    if os.path.exists(OUT):
        prev = pd.read_csv(OUT, dtype={"quadra6": str})
        done = set(prev["quadra6"].str[:3].unique())

    with open(OUT, "a", encoding="utf-8") as f:
        if not done:
            f.write("quadra6,latitude,longitude\n")
        for i, s in enumerate(setores, 1):
            if s in done:
                continue
            for tent in range(3):
                try:
                    quadras = fetch_setor(s)
                    n = 0
                    for key, (lat, lon) in quadras.items():
                        if key in needed:
                            f.write(f"{key},{lat},{lon}\n"); n += 1
                    f.flush()
                    print(f"[{i}/{len(setores)}] setor {s}: {n} quadras casadas", flush=True)
                    break
                except Exception as e:
                    print(f"[{i}/{len(setores)}] setor {s} tent {tent+1}: {str(e)[:50]}", flush=True)
                    time.sleep(3)
    print("CONCLUIDO.")


if __name__ == "__main__":
    main()
