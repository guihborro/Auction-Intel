"""
build_iptu_index.py — Índice de serving: SQL -> atributos cadastrais do IPTU.

Fonte: os próprios arquivos de ITBI (datasets/itbi_YYYY.xlsx), que carregam os
campos do IPTU (área construída, terreno, fração ideal, ano, padrão) por SQL.
Vantagem sobre a base cadastral avulsa: MESMA fonte/definições do treino ->
consistência treino/serving perfeita, e sem CAPTCHA. Cobertura = imóveis
transacionados nos anos incluídos (mais anos = mais cobertura).

Processa todos os anos disponíveis; ano mais recente vence no dedup por SQL.
Saída: datasets/iptu_index.csv  (sql11, area_construida, area_terreno,
fracao_ideal, idade, padrao).
"""
import glob
import os
import re

import pandas as pd

OUT = "datasets/iptu_index.csv"
ANO_BASE = 2024
SKIP_SHEETS = {"LEGENDA", "EXPLICAÇÕES", "Tabela de USOS", "Tabela de PADRÕES"}
# Índices de coluna no layout ITBI-IV (sem cabeçalho)
C_SQL, C_TERRENO, C_FRACAO, C_AREA, C_USO, C_PADRAO, C_ANO = 0, 19, 21, 22, 24, 26, 27


def parse_file(path):
    year = int(re.search(r"(\d{4})", os.path.basename(path)).group(1))
    xl = pd.ExcelFile(path)
    frames = []
    for sh in xl.sheet_names:
        if sh in SKIP_SHEETS:
            continue
        d = pd.read_excel(xl, sh, header=None)
        d = d[d[C_USO].astype(str).str.contains("APARTAMENTO", case=False, na=False)]
        if d.empty:
            continue
        out = pd.DataFrame({
            "sql11": d[C_SQL].astype("Int64").astype(str).str.zfill(11),
            "area_construida": pd.to_numeric(d[C_AREA], errors="coerce"),
            "area_terreno": pd.to_numeric(d[C_TERRENO], errors="coerce"),
            "fracao_ideal": pd.to_numeric(d[C_FRACAO], errors="coerce"),
            "ano_constr": pd.to_numeric(d[C_ANO], errors="coerce"),
            "padrao": d[C_PADRAO].astype(str),
        })
        out["_year"] = year
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    files = sorted(glob.glob("datasets/itbi_*.xlsx"))
    print(f"arquivos ITBI encontrados: {[os.path.basename(f) for f in files]}")
    if not files:
        print("nenhum datasets/itbi_*.xlsx — baixe ao menos um ano.")
        return

    parts = [parse_file(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna(subset=["sql11", "area_construida"])
    df = df[df["area_construida"] > 0]

    # dedup: ano mais recente vence
    df = df.sort_values("_year").drop_duplicates("sql11", keep="last")
    df["idade"] = (ANO_BASE - df["ano_constr"]).clip(0, 150)
    df["idade"] = df["idade"].fillna(df["idade"].median())
    df["fracao_ideal"] = df["fracao_ideal"].fillna(1.0)
    df["area_terreno"] = df["area_terreno"].fillna(0)

    idx = df[["sql11", "area_construida", "area_terreno", "fracao_ideal", "idade", "padrao"]]
    idx.to_csv(OUT, index=False)
    print(f"💾 {OUT}: {len(idx):,} imóveis (SQLs únicos)")
    print(f"   anos incluídos: {sorted(df['_year'].unique())}")


if __name__ == "__main__":
    main()
