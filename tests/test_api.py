"""Testes da API FastAPI.

Também servem de regressão para o efeito colateral de import: importar a
aplicação não deve carregar o modelo nem abrir o navegador. Na rota de
varredura, o scraper e os modelos são substituídos por dublês, então o teste
não acessa a rede nem depende dos .pkl.
"""

import pytest
from fastapi.testclient import TestClient

from auction_intel.api.main import app
from auction_intel.api.routes.analise import (
    get_engine_itbi,
    get_engine_market,
    get_tools,
)
from auction_intel.schemas.output import ImovelPreview

client = TestClient(app)


def test_health_ok():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_alive"] is True
    assert "version" in body


def test_import_nao_carrega_modelo_nem_scraper():
    # Se os providers lazy nunca foram chamados, o cache está vazio: prova de
    # que só importar a app não dispara o carregamento do .pkl.
    assert get_engine_market.cache_info().currsize == 0
    assert get_tools.cache_info().currsize == 0


class _FakeTools:
    def fetch_listings(self, url):
        return [
            ImovelPreview(
                title="Lote A", link="http://a", district="Moema", area_m2=70, auction_price=400_000
            ),
            ImovelPreview(
                title="Lote B",
                link="http://b",
                district="Santana",
                area_m2=50,
                auction_price=200_000,
            ),
        ]

    def get_geo_location(self, district):
        return {"lat": -23.6, "lon": -46.66}

    def fetch_cadastral_sql(self, link):
        return None


class _FakeMarket:
    # Lote A: 500 mil (ROI 25%); Lote B: 300 mil (ROI 50%)
    precos = {"Lote A": 500_000.0, "Lote B": 300_000.0}

    def predict_price(self, imovel, lat, lon):
        return self.precos[imovel.title]


class _FakeITBI:
    iptu = {}

    def predict(self, sql, area, lat, lon):
        return {"servable": True, "tier": "estimado", "price": area * 5_000.0}


@pytest.fixture
def api_com_dubles():
    app.dependency_overrides[get_tools] = _FakeTools
    app.dependency_overrides[get_engine_market] = _FakeMarket
    app.dependency_overrides[get_engine_itbi] = _FakeITBI
    yield client
    app.dependency_overrides.clear()


def test_varredura_calcula_roi_e_ordena(api_com_dubles):
    resp = api_com_dubles.post(
        "/api/v1/leiloes/varredura", json={"url": "https://exemplo.com/leiloes"}
    )
    assert resp.status_code == 200
    lotes = resp.json()

    # Ordenado do maior para o menor ROI
    assert [lote["title"] for lote in lotes] == ["Lote B", "Lote A"]
    assert lotes[0]["roi_potential"] == pytest.approx(50.0)
    assert lotes[1]["roi_potential"] == pytest.approx(25.0)

    # Piso ITBI entra como faixa, sem mexer no ROI
    assert lotes[0]["itbi_price"] == pytest.approx(250_000.0)
    assert lotes[0]["valuation_tier"] == "estimado"
