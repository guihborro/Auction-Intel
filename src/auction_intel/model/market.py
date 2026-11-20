"""
Valor de mercado (revenda) de um imóvel.

Carrega o modelo treinado em `training/train_market_model.py` (HistGradientBoosting
sobre preços de anúncio de apartamentos de São Paulo). A construção de features é
delegada a `auction_intel.features.engineering`, o mesmo módulo usado no treino, o que
garante as mesmas colunas, na mesma ordem, no treino e na inferência.
"""

import logging
from pathlib import Path

import joblib
import numpy as np

from auction_intel.config import settings
from auction_intel.features import engineering as features
from auction_intel.schemas.output import ImovelLeilao, ImovelPreview

logger = logging.getLogger(__name__)

DEFAULT_MODEL_FILENAME = "market_model.pkl"


class MarketValuationEngine:
    """Prevê o valor de mercado (R$) a partir das características do imóvel."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        if model_path is None:
            model_path = settings.MODELS_DIR / DEFAULT_MODEL_FILENAME

        logger.info("Carregando modelo de valor de mercado: %s", model_path)
        try:
            artifact = joblib.load(model_path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Modelo não encontrado em {model_path}. "
                "Rode `python training/train_market_model.py` para gerá-lo."
            ) from exc

        self.model = artifact["model"]
        self.landmarks = artifact.get("landmarks", features.ALL_LANDMARKS)
        self.feature_cols = artifact.get("feature_cols", features.feature_columns(self.landmarks))
        self.version = artifact.get("version", "unknown")
        self.metrics = artifact.get("metrics", {})
        logger.info(
            "Modelo %s carregado (R² teste=%s).", self.version, self.metrics.get("r2_test", "n/a")
        )

    def predict_price(self, imovel: ImovelLeilao | ImovelPreview, lat: float, lon: float) -> float:
        """Prevê o preço de mercado (R$) a partir do imóvel e das coordenadas."""
        if not self.model:
            return 0.0

        record = {
            "area": imovel.area_m2,
            "bedrooms": getattr(imovel, "bedrooms", 2),
            "bathrooms": getattr(imovel, "bathrooms", 1),
            "garage": getattr(imovel, "parking_spaces", 1),
            "latitude": lat,
            "longitude": lon,
            "district": imovel.district,
        }

        try:
            X = features.build_feature_frame(record, self.landmarks)
            log_price = self.model.predict(X)[0]
            return round(float(np.expm1(log_price)), 2)
        except Exception:
            logger.exception("Falha na predição do valor de mercado")
            return 0.0
