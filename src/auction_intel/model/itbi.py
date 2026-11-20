"""
engine_itbi.py — Piso de valor (ITBI, preço transacionado real), 2 tiers.

A partir da Inscrição da Prefeitura (SQL) — quando existe — + a área e a
coordenada do imóvel:

  1. CADASTRAL (~5%): SQL exato no índice IPTU -> features cadastrais reais
     (área construída, terreno, fração, idade, padrão) + geo da quadra -> modelo completo.
  2. ESTIMADO (~todos): modelo geo-only (área + coordenada + landmarks).
     A coordenada é a da QUADRA quando há SQL; senão a do BAIRRO (geocoding).
     Cobre até imóveis cujo edital não publica a Inscrição (ex.: Vila Prudente).

Sempre devolve um piso quando há área + alguma coordenada; só falha sem coordenada.
"""

import logging
import re

import joblib
import numpy as np
import pandas as pd

from auction_intel.config import settings
from auction_intel.features import engineering as features

logger = logging.getLogger(__name__)

MODEL_FULL = settings.MODELS_DIR / "itbi_model.pkl"
MODEL_GEO = settings.MODELS_DIR / "itbi_geo_model.pkl"
IPTU_INDEX = settings.DATASETS_DIR / "iptu_index.csv"
QUADRA_COORDS = settings.DATASETS_DIR / "quadra_coords.csv"


def normalize_sql(inscricao) -> str:
    """'123.456.7890-1' -> '12345678901' (11 dígitos). '' se ausente."""
    digits = re.sub(r"\D", "", str(inscricao)) if inscricao else ""
    return digits.zfill(11)[-11:] if digits else ""


class ValuationEngineITBI:
    def __init__(self, full=MODEL_FULL, geo=MODEL_GEO, index=IPTU_INDEX, quadra=QUADRA_COORDS):
        self.full = joblib.load(full)["model"]
        geo_art = joblib.load(geo)
        self.geo = geo_art["model"]
        self.geo_cols = geo_art["num_features"]  # ordem exata do treino (scaler é sensível)

        # Os CSVs de índice/quadra são grandes e opcionais em produção: sem eles,
        # o piso cai no tier "estimado" (geo-only) usando a coordenada do bairro.
        # Assim o deploy funciona só com os modelos (.pkl), sem os datasets.
        try:
            idx = pd.read_csv(index, dtype={"sql11": str})
            self.iptu = idx.set_index("sql11").to_dict("index")
        except Exception:
            self.iptu = {}
        try:
            q = pd.read_csv(quadra, dtype={"quadra6": str}).drop_duplicates("quadra6")
            self.quadra = {r.quadra6: (r.latitude, r.longitude) for r in q.itertuples()}
        except Exception:
            self.quadra = {}
        logger.info(
            "Piso ITBI carregado | índice IPTU: %s unidades | quadras: %s",
            len(self.iptu),
            len(self.quadra),
        )

    def _predict(self, model, rec, cols=None):
        df = features.add_engineered(pd.DataFrame([rec]))
        if cols is not None:
            df = df[cols]  # scaler puro exige nomes+ordem exatos
        return round(float(np.expm1(model.predict(df)[0])), 2)

    def predict(self, inscricao=None, area_anuncio=None, lat=None, lon=None) -> dict:
        """Retorna {tier, servable, price, ...}. Não levanta em caso de miss."""
        sql11 = normalize_sql(inscricao)
        quadra6 = sql11[:6] if sql11 else ""
        attrs = self.iptu.get(sql11) if sql11 else None
        qcoord = self.quadra.get(quadra6) if quadra6 else None

        # Tier 1: CADASTRAL (SQL exato + quadra)
        if attrs is not None and qcoord is not None:
            rec = {
                "area": attrs["area_construida"],
                "area_terreno": attrs["area_terreno"],
                "fracao_ideal": attrs["fracao_ideal"],
                "idade": attrs["idade"],
                "latitude": qcoord[0],
                "longitude": qcoord[1],
                "setor": sql11[:3],
                "padrao": attrs["padrao"],
            }
            return {
                "servable": True,
                "tier": "cadastral",
                "price": self._predict(self.full, rec),
                "sql11": sql11,
                "area_usada": attrs["area_construida"],
            }

        # Tier 2: ESTIMADO (geo-only) — coord da quadra se houver, senão do bairro
        coord = qcoord or ((lat, lon) if lat and lon else None)
        if area_anuncio and area_anuncio > 0 and coord:
            rec = {"area": float(area_anuncio), "latitude": coord[0], "longitude": coord[1]}
            price = self._predict(self.geo, rec, cols=self.geo_cols)
            return {
                "servable": True,
                "tier": "estimado",
                "price": price,
                "sql11": sql11 or None,
                "area_usada": float(area_anuncio),
            }

        return {"servable": False, "tier": None, "reason": "sem área ou coordenada"}
