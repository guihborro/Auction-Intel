"""Testes do módulo de features compartilhado (train/serve sem skew)."""
import numpy as np
import pandas as pd
import pytest

from auction_intel.features import engineering as features


class TestHaversine:
    def test_mesmo_ponto_e_zero(self):
        assert features.haversine_np(-23.55, -46.63, -23.55, -46.63) == pytest.approx(0.0, abs=1e-6)

    def test_um_grau_latitude_aprox_111km(self):
        assert features.haversine_np(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.19, abs=1.0)


class TestFeatureColumns:
    def test_tamanho_e_ordem(self):
        cols = features.feature_columns()
        # 7 numéricas base + 15 landmarks (9 + 6 metrô) + 1 categórica
        assert len(cols) == 7 + len(features.ALL_LANDMARKS) + 1
        assert cols[0] == "area"
        assert "log_area" in cols
        assert cols[-1] == "district"

    def test_landmarks_incluem_metro(self):
        cols = features.feature_columns()
        assert "dist_metro_paulista" in cols
        assert "dist_faria_lima" in cols


class TestBuildFeatureFrame:
    def _record(self):
        return {
            "area": 60.0,
            "bedrooms": 2,
            "bathrooms": 2,
            "garage": 1,
            "latitude": -23.5629,
            "longitude": -46.6544,
            "district": "Pinheiros",
        }

    def test_dict_gera_uma_linha_com_todas_as_colunas(self):
        X = features.build_feature_frame(self._record())
        assert list(X.columns) == features.feature_columns()
        assert len(X) == 1

    def test_log_area_calculado(self):
        X = features.build_feature_frame(self._record())
        assert X["log_area"].iloc[0] == pytest.approx(np.log1p(60.0))

    def test_consistencia_dict_vs_dataframe(self):
        # Construir via dict único deve dar o mesmo resultado que via DataFrame:
        # é justamente o que garante ausência de skew entre treino e inferência.
        rec = self._record()
        via_dict = features.build_feature_frame(rec)
        via_df = features.build_feature_frame(pd.DataFrame([rec]))
        num_cols = features.numeric_features()
        np.testing.assert_allclose(via_dict[num_cols].values, via_df[num_cols].values)
        assert via_dict["district"].iloc[0] == via_df["district"].iloc[0]


class TestNormalizacaoBairro:
    def test_remove_acento_caixa_e_zona(self):
        assert features.norm_district("Tatuapé (Zona Leste)") == "tatuape"

    def test_valor_nao_texto_vira_vazio(self):
        assert features.norm_district(None) == ""

    def test_frame_devolve_uma_coluna_district(self):
        out = features.normalize_district_frame(pd.DataFrame({"district": ["Vila Mariana", "MOEMA"]}))
        assert list(out.columns) == ["district"]
        assert out["district"].tolist() == ["vila mariana", "moema"]
