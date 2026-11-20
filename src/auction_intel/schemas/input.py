from pydantic import BaseModel, Field

class AnaliseRequest(BaseModel):
    """Schema para o payload recebido pelo endpoint de análise."""
    url: str = Field(
        ...,
        description="URL da listagem de leilões para realizar a varredura.",
        example="https://www.megaleiloes.com.br/imoveis/apartamentos/sp/sao-paulo"
    )


class EditalRequest(BaseModel):
    """Payload para análise do edital de um lote específico."""
    link: str = Field(..., description="URL da página de detalhe do lote.")