"""
build_dataset_2024.py — Normaliza a base "Image-Based Property Price Prediction
in São Paulo" (Kaggle, abril/2024) para o schema do modelo.

Produz `datasets/sp2024_normalized.csv` com:
  * colunas de PARIDADE: area, bedrooms, bathrooms, garage, latitude, longitude,
    district, price  (as colunas usadas pelo modelo de mercado);
  * colunas RICAS extras: category, iptu, condo, n_amenities + flags de comodidade;

Decisões de geolocalização (documentadas):
  A base 2024 NÃO tem lat/lon — só bairro. Em vez de geocodificar 900+ bairros
  (lento e ruidoso), atribuímos a cada imóvel o CENTROIDE do seu bairro calculado
  a partir da base atual (`dataset_under_7M.csv`). Vantagem dupla: (1) offline e
  determinístico; (2) coloca a base 2024 no MESMO sistema de coordenadas da base
  atual, tornando-as compatíveis para combinar. Bairros sem correspondência
  (~16%) são descartados para não injetar ruído de geocoding.
"""

import re
import unicodedata

import pandas as pd

SRC_2024 = "datasets/sp_2024_image_based.csv"
BASE_ATUAL = "datasets/dataset_under_7M.csv"
OUT = "datasets/sp2024_normalized.csv"

# Faixas de limpeza (espelham filter_under_7m.py)
PRICE_MIN, PRICE_MAX = 50_000, 7_000_000
AREA_MIN, AREA_MAX = 15, 700

AMENITIES = [
    "Academia",
    "Elevador",
    "Permitido animais",
    "Piscina",
    "Portaria",
    "Salão de festas",
    "Condomínio fechado",
    "Segurança 24h",
    "Portão eletrônico",
    "Área murada",
    "Área de serviço",
    "Armários na cozinha",
    "Armários no quarto",
    "Churrasqueira",
    "Mobiliado",
    "Quarto de serviço",
    "Ar condicionado",
    "Porteiro 24h",
    "Varanda",
]


def norm_district(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", "", s)  # remove "(Zona X)"
    s = re.sub(r"[^a-zA-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def to_num(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace("5 ou mais", "5", regex=False)
    return pd.to_numeric(s, errors="coerce")


def main():
    print(f"📥 Lendo {SRC_2024}...")
    b = pd.read_csv(SRC_2024, sep=";", encoding="utf-8-sig")
    print(f"   {len(b)} linhas brutas.")

    b = b.rename(
        columns={
            "Área útil": "area",
            "Quartos": "bedrooms",
            "Banheiros": "bathrooms",
            "Vagas na garagem": "garage",
            "bairro": "district",
            "Categoria": "category",
            "IPTU": "iptu",
            "Condomínio": "condo",
        }
    )

    for c in ["area", "bedrooms", "bathrooms", "garage", "price", "iptu", "condo"]:
        b[c] = to_num(b[c])

    # Limpeza de faixa
    b = b.dropna(subset=["area", "price"])
    b = b[
        (b.price >= PRICE_MIN) & (b.price <= PRICE_MAX) & (b.area > AREA_MIN) & (b.area < AREA_MAX)
    ]
    print(f"   {len(b)} após limpeza de faixa (preço/área).")

    # Imputação simples dos inteiros faltantes (mediana) — StandardScaler não aceita NaN
    for c in ["bedrooms", "bathrooms", "garage"]:
        med = int(b[c].median())
        b[c] = b[c].fillna(med).round().astype(int)
    b["iptu"] = b["iptu"].fillna(b["iptu"].median())
    b["condo"] = b["condo"].fillna(0.0)  # sem condomínio (comum em casas)

    # Comodidades -> 0/1 + contagem
    present = [a for a in AMENITIES if a in b.columns]
    for a in present:
        b[a] = pd.to_numeric(b[a], errors="coerce").fillna(0).astype(int).clip(0, 1)
    b["n_amenities"] = b[present].sum(axis=1)

    # ── Geolocalização por centroide de bairro (da base atual) ──────────────
    a = pd.read_csv(BASE_ATUAL)
    a["dnorm"] = a["district"].map(norm_district)
    centroids = a.groupby("dnorm")[["latitude", "longitude"]].mean()
    b["dnorm"] = b["district"].map(norm_district)
    b = b.join(centroids, on="dnorm")
    antes = len(b)
    b = b.dropna(subset=["latitude", "longitude"])
    print(f"   {len(b)}/{antes} com centroide de bairro ({100 * len(b) / antes:.1f}%).")

    # District canônico (usar a forma normalizada, consistente com a base atual)
    b["district"] = b["dnorm"]

    # Dedup só de duplicatas verdadeiras (idênticas em todas as features de
    # imóvel). Não usamos lat/lon na chave porque, sendo centroides de bairro,
    # colapsariam imóveis distintos do mesmo bairro.
    b = b.drop_duplicates(
        subset=["price", "area", "bedrooms", "bathrooms", "garage", "district", "category"]
    )

    cols = [
        "area",
        "bedrooms",
        "bathrooms",
        "garage",
        "latitude",
        "longitude",
        "district",
        "price",
        "category",
        "iptu",
        "condo",
        "n_amenities",
    ] + present
    b = b[cols]
    b.to_csv(OUT, index=False, encoding="utf-8")
    print(f"💾 Salvo: {OUT}  ({len(b)} linhas, {len(cols)} colunas)")
    print(
        f"   apartamentos: {(b.category == 'Apartamentos').sum()} | casas: {(b.category == 'Casas').sum()}"
    )


if __name__ == "__main__":
    main()
