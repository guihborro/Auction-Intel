"""Cálculo de retorno sobre o lance."""


def roi_potencial(valor_mercado: float, lance: float) -> float:
    """ROI bruto (%) de comprar pelo lance e revender pelo valor de mercado.

    Retorna 0.0 quando o lance não é positivo (lote sem preço informado).
    """
    if lance <= 0:
        return 0.0
    return (valor_mercado - lance) / lance * 100
