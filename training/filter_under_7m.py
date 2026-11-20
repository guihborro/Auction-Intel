"""
filter_under_7m.py — Limpa a base antiga de anúncios (datasets/dataset.csv).

Gera datasets/dataset_under_7M.csv, usado por build_dataset_2024.py (centroides de
bairro) e por compare_datasets.py. Filtros: preço entre R$ 50 mil e R$ 7 milhões,
área entre 15 e 700 m², latitude dentro do município e remoção de duplicatas.
"""

import os

import pandas as pd

INPUT_FILE = "datasets/dataset.csv"
OUTPUT_FILE = "datasets/dataset_under_7M.csv"


def extract_district(address):
    if not isinstance(address, str):
        return "Desconhecido"
    try:
        parte_local = address.split(" - ")[0]
        if "," in parte_local:
            bairro = parte_local.split(",")[-1]
        else:
            bairro = parte_local
        return bairro.strip().title()
    except Exception:
        return "Desconhecido"


def filtrar_base():
    print("Gerando base filtrada (R$ 50 mil a R$ 7 milhões)...")

    if not os.path.exists(INPUT_FILE):
        print(f"❌ Erro: {INPUT_FILE} não encontrado.")
        return

    try:
        df = pd.read_csv(INPUT_FILE)
        df.columns = df.columns.str.lower().str.strip()
    except Exception as e:
        print(f"❌ Erro ao ler CSV: {e}")
        return

    # Normaliza Colunas
    mapa_colunas = {
        "price": "price",
        "sale price": "price",
        "valor": "price",
        "area": "area",
        "useful area": "area",
        "adress": "address",
        "address": "address",
        "bedrooms": "bedrooms",
        "quartos": "bedrooms",
        "bathrooms": "bathrooms",
        "banheiros": "bathrooms",
        "parking_spaces": "garage",
        "garage": "garage",
        "vagas": "garage",
        "latitude": "latitude",
        "lat": "latitude",
        "longitude": "longitude",
        "lng": "longitude",
        "long": "longitude",
    }
    df = df.rename(columns=mapa_colunas)

    if "address" in df.columns:
        df["district"] = df["address"].apply(extract_district)

    cols_num = ["price", "area", "bedrooms", "bathrooms", "garage", "latitude", "longitude"]
    for col in cols_num:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=cols_num)

    print("Aplicando filtros...")

    df_filtered = df[
        (df["price"] >= 50000)
        & (df["price"] <= 7000000)
        & (df["area"] > 15)
        & (df["area"] < 700)
        & (df["latitude"] < -23.0)
        & (df["latitude"] > -24.5)
    ]

    # Remove Duplicatas
    df_filtered = df_filtered.drop_duplicates(
        subset=["price", "area", "bedrooms", "latitude", "longitude"]
    )

    final_len = len(df_filtered)

    cols_finais = [
        "area",
        "bedrooms",
        "bathrooms",
        "garage",
        "latitude",
        "longitude",
        "district",
        "price",
    ]
    df_filtered = df_filtered[cols_finais]

    df_filtered.to_csv(OUTPUT_FILE, index=False)

    print("-" * 40)
    print("✅ CONCLUÍDO!")
    print(f"📂 Arquivo gerado: {OUTPUT_FILE}")
    print("-" * 40)
    print(f"📊 Total de Imóveis: {final_len}")
    print(f"💰 Maior Preço: R$ {df_filtered['price'].max():,.2f}")


if __name__ == "__main__":
    filtrar_base()
