from fastapi import APIRouter
from pydantic import BaseModel

# Criamos o schema de output diretamente aqui por ser muito simples e exclusivo desta rota,
# mas também podes colocá-lo no `app/schemas/output.py` se preferires isolar 100%.
class HealthOutput(BaseModel):
    is_alive: bool
    version: str
    author: str

router = APIRouter()

@router.get(
    "/health",
    response_model=HealthOutput,
    name="health",
)
def get_health() -> HealthOutput:
    """
    ### Verificação de Saúde da API (`/health`)

    Esta rota permite verificar se a API está a operar corretamente
    e acessível.

    ---

    #### O que essa rota valida:
    - Verifica se o serviço FastAPI está ativo e a funcionar.
    - Exibe a versão da aplicação em execução.
    - Retorna informações do autor/responsável técnico.

    ---

    #### Resposta (200 OK)

    ```json
    {
      "is_alive": true,
      "version": "1.0.0",
      "author": "Auction Intel"
    }
    ```

    - `is_alive`: Confirma se a API está funcional (`true` ou `false`).
    - `version`: Versão atual da aplicação.
    - `author`: Nome e e-mail do responsável técnico ou equipa da API.

    ---

    #### Observações
    - Útil para ferramentas de monitorização, orquestradores (como Kubernetes), CI/CD
      e validação de disponibilidade.
    - Pode ser usada como endpoint de **health check** em balanceadores de carga.
    """

    # Retornamos os dados diretamente para não dependermos de configurações externas complexas nesta fase de MVP
    health = HealthOutput(
        is_alive=True,
        version="1.0.0",
        author="Auction Intel / Guilherme"
    )

    return health