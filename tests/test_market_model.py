"""Testes de integração do modelo de valor de mercado (models/market_model.pkl)."""

import pytest

from auction_intel.config import settings
from auction_intel.schemas.output import ImovelPreview

_PKL = settings.MODELS_DIR / "market_model.pkl"

pytestmark = pytest.mark.skipif(not _PKL.exists(), reason=f"{_PKL} ausente")

# Coordenadas próximas à Av. Paulista
LAT, LON = -23.5629, -46.6544


@pytest.fixture(scope="module")
def engine():
    from auction_intel.model.market import MarketValuationEngine

    return MarketValuationEngine()


def _imovel(area: float = 60.0, district: str = "Pinheiros") -> ImovelPreview:
    return ImovelPreview(
        title="Apto teste",
        link="http://exemplo",
        district=district,
        area_m2=area,
        auction_price=500_000.0,
        bedrooms=2,
        bathrooms=2,
        parking_spaces=1,
    )


def test_preco_positivo_e_plausivel(engine):
    preco = engine.predict_price(_imovel(), LAT, LON)
    # Um apartamento em SP não vale centavos nem centenas de milhões.
    assert 50_000 < preco < 20_000_000


def test_area_maior_tende_a_preco_maior(engine):
    assert engine.predict_price(_imovel(area=120.0), LAT, LON) > engine.predict_price(
        _imovel(area=45.0), LAT, LON
    )


def test_bairro_e_normalizado_antes_do_target_encoding(engine):
    # Caixa, acentos e espaços não podem mudar o encoding do bairro.
    precos = {
        engine.predict_price(_imovel(district=d), LAT, LON)
        for d in ("Pinheiros", "PINHEIROS", "  pinheiros ")
    }
    assert len(precos) == 1


def test_bairro_desconhecido_nao_quebra(engine):
    # O TargetEncoder usa a média global para categorias nunca vistas.
    preco = engine.predict_price(_imovel(district="Bairro Que Nao Existe"), LAT, LON)
    assert preco > 0
