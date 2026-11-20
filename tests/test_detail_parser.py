"""Testes do parser da página de detalhe do leilão (parse_detail_fields).

Os textos abaixo seguem o formato dos anúncios do Mega Leilões, com
endereço, matrícula, inscrição e nomes trocados por dados fictícios.
"""
from auction_intel.collection.scraper import parse_detail_fields

# Anúncio 1: tem avaliação, SQL cadastral e ocupação na descrição
TXT_1 = (
    "Área 51 m2 Localização Rua das Flores, 100, Conjunto Residencial "
    "Jardim Exemplo, São Paulo, SP Comitente BANCO EXEMPLO S.A. Leiloeiro "
    "Fulano de Tal Valor de Avaliação R$ 195.000,00 ( Cento e noventa e cinco mil reais) . "
    "Descrição Apartamento 12-B Condomínio Exemplo - Integrante Do Conj. Hab. "
    "Jardim Exemplo, Padrão, Ocupado. Área(s): 51,34 m² de área construída. "
    "Matrícula(s): 100.000. Cartório: 9º CRI DE SÃO PAULO. "
    "Inscrição da Prefeitura: 123.456.7890-1 ISENTO. "
    "Para imóveis DESOCUPADOS, as visitas deverão ser agendadas."
)

# Anúncio 2: avaliação "não informada" (R$ 0,00) e ocupação em caixa alta
TXT_2 = (
    "Localização Rua Exemplo, 50, Vila Fictícia, São Paulo Comitente XPTO "
    "Valor de Avaliação R$ 0,00 ( Nao informado) OCUPADO "
    "Para imóveis DESOCUPADOS, as visitas deverão ser agendadas."
)


class TestParseDetailFields:
    def test_endereco_anuncio_1(self):
        r = parse_detail_fields(TXT_1)
        assert r["full_address"] == "Rua das Flores, 100, Conjunto Residencial Jardim Exemplo, São Paulo, SP"

    def test_ocupacao_anuncio_1(self):
        assert parse_detail_fields(TXT_1)["occupancy"] == "Ocupado"

    def test_avaliacao_anuncio_1(self):
        assert parse_detail_fields(TXT_1)["appraisal_value"] == 195000.0

    def test_sql_cadastral_anuncio_1(self):
        assert parse_detail_fields(TXT_1)["cadastral_sql"] == "123.456.7890-1"

    def test_endereco_anuncio_2(self):
        assert parse_detail_fields(TXT_2)["full_address"] == "Rua Exemplo, 50, Vila Fictícia, São Paulo"

    def test_ocupacao_anuncio_2_caixa_alta(self):
        assert parse_detail_fields(TXT_2)["occupancy"] == "Ocupado"

    def test_avaliacao_zero_vira_none(self):
        assert parse_detail_fields(TXT_2)["appraisal_value"] is None

    def test_boilerplate_nao_marca_desocupado(self):
        # A frase "Para imóveis DESOCUPADOS..." é institucional e não deve
        # sobrescrever a ocupação real do imóvel.
        assert parse_detail_fields(TXT_1)["occupancy"] == "Ocupado"

    def test_texto_vazio(self):
        r = parse_detail_fields("")
        assert r == {"full_address": None, "occupancy": None, "appraisal_value": None, "cadastral_sql": None}
