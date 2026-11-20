"""Testes unitários das funções puras de extração/inferência em AuctionTools.

Nenhum destes testes acessa a rede ou o navegador: exercitam apenas a lógica
determinística de parsing e imputação estatística.
"""

import pytest

from auction_intel.collection.scraper import AuctionTools


@pytest.fixture(scope="module")
def tools():
    # AuctionTools.__init__ apenas monta BrowserService/GeocodingService;
    # não abre navegador nem carrega modelo, então é barato instanciar.
    return AuctionTools()


class TestExtractNumber:
    def test_preco_formato_brasileiro(self, tools):
        assert tools._extract_number("R$ 350.000,00") == 350000.0

    def test_area_com_unidade(self, tools):
        assert tools._extract_number("120 m²") == 120.0

    def test_decimal_com_virgula(self, tools):
        assert tools._extract_number("1,5") == 1.5

    def test_texto_vazio(self, tools):
        assert tools._extract_number("") == 0.0

    def test_none(self, tools):
        assert tools._extract_number(None) == 0.0

    def test_texto_sem_numero(self, tools):
        assert tools._extract_number("consulte-nos") == 0.0


class TestInferFeaturesFromArea:
    def test_area_zero_retorna_default_minimo(self, tools):
        assert tools._infer_features_from_area(0) == {
            "bedrooms": 1,
            "bathrooms": 1,
            "garage": 0,
        }

    def test_binning_para_dezena(self, tools):
        # 55 m² cai no bin de 50 m²
        assert tools._infer_features_from_area(55) == {
            "bedrooms": 2,
            "bathrooms": 1,
            "garage": 1,
        }

    def test_clamp_abaixo_do_minimo(self, tools):
        # 5 m² é menor que o menor bin (20 m²) e deve ser fixado nele
        assert tools._infer_features_from_area(5) == tools._infer_features_from_area(20)

    def test_clamp_acima_do_maximo(self, tools):
        # 9999 m² deve ser fixado no maior bin (670 m²)
        assert tools._infer_features_from_area(9999) == tools._infer_features_from_area(670)

    def test_bin_intermediario_ausente_usa_fallback(self, tools):
        # 525 -> bin 520 não existe no mapa; deve cair no fallback padrão.
        assert tools._infer_features_from_area(525) == {
            "bedrooms": 2,
            "bathrooms": 1,
            "garage": 1,
        }
