"""
Engenharia de features compartilhada entre treino e inferência.

Este módulo existe para eliminar o *train/serve skew*: exatamente o mesmo código
de features é usado no treino (`training/train_market_model.py`) e na inferência
(`auction_intel.model.market`). Se uma feature muda aqui, muda nos dois lugares.

Features:
  * distâncias de Haversine a marcos valorizados e estações de metrô;
  * `log_area` (relação não-linear entre área e preço);
  * o bairro (`district`) é entregue cru: o encoding é aprendido dentro do
    próprio Pipeline (sklearn TargetEncoder, com cross-fitting anti-vazamento),
    então não é preciso salvar um dicionário de médias à parte.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

# ── Marcos valorizados ────────────────────────────────────────
LANDMARKS: dict[str, tuple[float, float]] = {
    "dist_faria_lima": (-23.5856, -46.6823),
    "dist_paulista": (-23.5629, -46.6544),
    "dist_berrini": (-23.6006, -46.6967),
    "dist_ibirapuera": (-23.5874, -46.6576),
    "dist_iguatemi": (-23.5772, -46.6908),
    "dist_cid_jardim": (-23.6015, -46.6976),
    "dist_tatuape": (-23.5403, -46.5768),
    "dist_santana": (-23.5028, -46.6253),
    "dist_centro_hist": (-23.5505, -46.6333),
}

# ── Estações de metrô ──────────────────────────
METRO_LANDMARKS: dict[str, tuple[float, float]] = {
    "dist_metro_faria_lima": (-23.5867, -46.6817),  # L4 Amarela
    "dist_metro_paulista": (-23.5644, -46.6527),  # L2 Verde / L4 Amarela
    "dist_metro_vila_madalena": (-23.5534, -46.6902),  # L2 Verde
    "dist_metro_tatuape": (-23.5417, -46.5745),  # L3 Vermelha
    "dist_metro_santana": (-23.5027, -46.6284),  # L1 Azul
    "dist_metro_bras": (-23.5403, -46.6128),  # L3 Vermelha
}

ALL_LANDMARKS: dict[str, tuple[float, float]] = {**LANDMARKS, **METRO_LANDMARKS}

# ── Definição das colunas de features ───────────────────────────────────────
NUMERIC_BASE: list[str] = [
    "area",
    "log_area",
    "bedrooms",
    "bathrooms",
    "garage",
    "latitude",
    "longitude",
]
CATEGORICAL: list[str] = ["district"]

EARTH_RADIUS_KM = 6371.0


def haversine_np(lat1, lon1, lat2, lon2):
    """Distância Haversine (km) — vetorizada, aceita escalares ou arrays."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dlambda = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def norm_district(s) -> str:
    """Normaliza nome de bairro: sem acento, sem '(Zona X)', minúsculo, só letras.

    Precisa ser idêntico no treino e na inferência — por isso vive aqui. É usado
    tanto na preparação do dataset quanto (via FunctionTransformer) dentro do
    próprio Pipeline do modelo, de forma que o bairro cru vindo do scraper seja
    normalizado do mesmo jeito antes do TargetEncoder.
    """
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-zA-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_district_frame(X):
    """Normaliza a coluna de bairro; devolve DataFrame 1-coluna (para o encoder).

    Definida no nível do módulo (não como lambda) para ser picklável junto do
    modelo — o FunctionTransformer referencia esta função por caminho de import.
    """
    col = X.iloc[:, 0] if hasattr(X, "iloc") else pd.Series(np.asarray(X).ravel())
    return col.map(norm_district).to_frame("district")


def numeric_features(landmarks: Mapping[str, tuple[float, float]] = ALL_LANDMARKS) -> list[str]:
    """Colunas numéricas na ordem canônica (base + distâncias dos landmarks)."""
    return NUMERIC_BASE + list(landmarks.keys())


def feature_columns(landmarks: Mapping[str, tuple[float, float]] = ALL_LANDMARKS) -> list[str]:
    """Todas as colunas de entrada do modelo (numéricas + categórica)."""
    return numeric_features(landmarks) + CATEGORICAL


def add_engineered(
    df: pd.DataFrame, landmarks: Mapping[str, tuple[float, float]] = ALL_LANDMARKS
) -> pd.DataFrame:
    """Adiciona `log_area` e as distâncias para cada landmark (não muta o input)."""
    df = df.copy()
    df["log_area"] = np.log1p(df["area"])
    for name, (lat_ref, lon_ref) in landmarks.items():
        df[name] = haversine_np(df["latitude"], df["longitude"], lat_ref, lon_ref)
    return df


def build_feature_frame(
    records: pd.DataFrame | Mapping | Sequence[Mapping],
    landmarks: Mapping[str, tuple[float, float]] = ALL_LANDMARKS,
) -> pd.DataFrame:
    """Constrói o DataFrame de features pronto para `model.predict`.

    Aceita um único registro (dict), uma lista de dicts ou um DataFrame com as
    colunas cruas (`area, bedrooms, bathrooms, garage, latitude, longitude,
    district`). Retorna apenas as colunas de `feature_columns`, na ordem certa.
    """
    if isinstance(records, pd.DataFrame):
        df = records.copy()
    elif isinstance(records, Mapping):
        df = pd.DataFrame([dict(records)])
    else:
        df = pd.DataFrame([dict(r) for r in records])

    df = add_engineered(df, landmarks)
    return df[feature_columns(landmarks)]
