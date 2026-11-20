from typing import Literal, Optional
from pydantic import BaseModel, Field

# Mantido do seu código original
class ImovelPreview(BaseModel):
    """Schema otimizado para a listagem inicial e resultado do Motor ML (UC01 e UC02)."""
    title: str = Field(..., description="Título do anúncio.")
    link: str = Field(..., description="URL para detalhes.")
    district: str = Field(..., description="Bairro.")
    area_m2: float = Field(..., description="Área útil.")
    auction_price: float = Field(..., description="Valor atual.")
    
    bedrooms: int = Field(2, description="Quartos estimados.")
    parking_spaces: int = Field(1, description="Vagas estimadas.")
    bathrooms: Optional[int] = Field(1, description="Banheiros (Injetado via inferência).") 
    
    image_url: Optional[str] = Field(None, description="URL da imagem do card.")

    # Enriquecidos a partir da PÁGINA DE DETALHE (opcionais — item pode vir só do card)
    full_address: Optional[str] = Field(None, description="Endereço completo (página de detalhe).")
    occupancy: Optional[str] = Field(None, description="Ocupação: 'Ocupado' / 'Desocupado'.")
    appraisal_value: Optional[float] = Field(None, description="Valor de avaliação (R$), quando informado.")
    latitude: Optional[float] = Field(None, description="Latitude precisa (geocoding do endereço).")
    longitude: Optional[float] = Field(None, description="Longitude precisa (geocoding do endereço).")

    cadastral_sql: Optional[str] = Field(None, description="Inscrição/SQL cadastral (página de detalhe).")

    # Preenchidos dinamicamente pelo ValuationEngine
    ml_predicted_price: Optional[float] = Field(None, description="Valor de mercado previsto pelo modelo. Base do ROI.")
    roi_potential: Optional[float] = Field(None, description="Retorno sobre investimento (%) — baseado no Preço ML.")
    itbi_price: Optional[float] = Field(None, description="Valor calibrado ITBI (só comparação, não afeta o ROI).")
    valuation_tier: Optional[str] = Field(None, description="Tier do piso ITBI: cadastral ou estimado (None se indisponível).")

class DossieEdital(BaseModel):
    """Dossiê jurídico do edital + matrícula (via LLM), explicado para leigos."""
    ok: bool = Field(..., description="True se a análise foi concluída.")
    reason: Optional[str] = Field(None, description="Motivo quando ok=False.")

    # ── Fatos estruturados ────────────────────────────────────────────────
    tipo_leilao: Optional[str] = Field(None, description="Judicial / Extrajudicial.")
    tipo_direito: Optional[str] = Field(None, description="Propriedade plena / Somente direitos aquisitivos.")
    ocupacao: Optional[str] = Field(None, description="Ocupado / Desocupado / Não informado.")
    prazo_desocupacao: Optional[str] = Field(None, description="Prazo/condição de desocupação, se houver.")
    valor_avaliacao: Optional[float] = Field(None, description="Valor de avaliação (R$), se no edital.")
    debito_iptu: Optional[float] = Field(None, description="Débito de IPTU (R$).")
    debito_condominio: Optional[float] = Field(None, description="Débito de condomínio (R$).")
    divida_ativa: Optional[float] = Field(None, description="Débitos em dívida ativa (R$).")
    debitos_responsavel: Optional[str] = Field(None, description="Quem quita: arrematante / vendedor / não informado.")
    debito_total_arrematante: Optional[float] = Field(None, description="Soma dos débitos por conta do arrematante (R$).")
    condicoes_pagamento: Optional[str] = Field(None, description="À vista/parcelado, entrada etc. (linguagem simples).")
    comissao_leiloeiro: Optional[str] = Field(None, description="Comissão do leiloeiro (ex.: '5%').")
    onus_gravames: list = Field(default_factory=list, description="Ônus reais na matrícula (hipoteca, penhora, usufruto…).")
    aceita_financiamento: Optional[bool] = Field(None, description="Se aceita financiamento/parcelamento.")

    # ── Camada "para leigos" ──────────────────────────────────────────────
    nivel_risco: Optional[str] = Field(None, description="Baixo / Médio / Alto.")
    resumo_leigo: Optional[str] = Field(None, description="Explicação da situação em linguagem simples.")
    pontos_positivos: list = Field(default_factory=list, description="Pontos a favor, em linguagem simples.")
    pontos_atencao: list = Field(default_factory=list, description="Riscos EXPLICADOS em linguagem simples.")
    glossario: list = Field(default_factory=list, description="Termos jurídicos deste edital: [{termo, explicacao}].")
    recomendacao: Optional[str] = Field(None, description="Veredito em linguagem simples + porquê.")

    fonte_pdfs: list = Field(default_factory=list, description="PDFs analisados (edital, matrícula).")


class ImovelLeilao(BaseModel):
    """Reservado para Fase Futura: Extração profunda do Edital"""
    full_address: str = Field(..., description="Endereço completo.")
    district: str = Field(..., description="Bairro.")
    area_m2: float = Field(..., description="Área.")
    bedrooms: int = Field(..., description="Quartos.")
    bathrooms: int = Field(..., description="Banheiros.")
    parking_spaces: int = Field(..., description="Vagas.")
    auction_price: float = Field(..., description="Preço Leilão.")
    appraisal_value: float = Field(..., description="Avaliação.")
    condo_debt: float = 0.0
    tax_debt: float = 0.0
    is_occupied: bool = Field(..., description="Ocupação.")
    conservation_state: Literal['Ruim', 'Regular', 'Bom', 'Ótimo', 'Desconhecido']
    description_summary: str
