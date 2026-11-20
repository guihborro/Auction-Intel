"""Testes do cálculo de ROI."""

import pytest

from auction_intel.roi.calc import roi_potencial


def test_lucro_de_50_porcento():
    assert roi_potencial(valor_mercado=300_000, lance=200_000) == pytest.approx(50.0)


def test_prejuizo_fica_negativo():
    assert roi_potencial(valor_mercado=150_000, lance=200_000) == pytest.approx(-25.0)


def test_valor_igual_ao_lance_e_zero():
    assert roi_potencial(valor_mercado=200_000, lance=200_000) == 0.0


@pytest.mark.parametrize("lance", [0.0, -1.0])
def test_lance_nao_positivo_devolve_zero(lance):
    assert roi_potencial(valor_mercado=300_000, lance=lance) == 0.0
