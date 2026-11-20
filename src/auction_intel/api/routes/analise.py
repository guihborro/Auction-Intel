import json
import logging
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from auction_intel.collection.scraper import AuctionTools
from auction_intel.db import models
from auction_intel.db.database import get_db
from auction_intel.edital.agent import EditalAgent
from auction_intel.model.itbi import ValuationEngineITBI
from auction_intel.model.market import MarketValuationEngine
from auction_intel.roi.calc import roi_potencial
from auction_intel.schemas.input import AnaliseRequest, EditalRequest
from auction_intel.schemas.output import DossieEdital, ImovelPreview

logger = logging.getLogger(__name__)

router = APIRouter()

# O valor de MERCADO (revenda) vem do modelo treinado sobre preços de anúncio e é a
# base do ROI. O ITBI (preço declarado ao fisco) entra como PISO conservador.


# ─────────────────────────────────────────────────────────────────────────────
# Providers (lazy singletons)
#
# As ferramentas são instanciadas sob demanda, na primeira requisição, e não
# mais no momento em que este módulo é importado. Isso evita o efeito colateral
# de carregar o modelo de ML (~pkl) só de importar o pacote — o que
# atrapalhava testes e a inicialização. O @lru_cache garante uma única instância
# reaproveitada entre requisições.
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_tools() -> AuctionTools:
    return AuctionTools()


@lru_cache(maxsize=1)
def get_engine_market() -> MarketValuationEngine:
    """Motor de valor de mercado (preço de anúncio)."""
    return MarketValuationEngine()


@lru_cache(maxsize=1)
def get_engine_itbi() -> ValuationEngineITBI:
    return ValuationEngineITBI()


@lru_cache(maxsize=1)
def get_edital_agent() -> EditalAgent:
    return EditalAgent()


@router.post("/edital", response_model=DossieEdital, name="analise:analisar_edital")
def analisar_edital(
    req: EditalRequest,
    agent: EditalAgent = Depends(get_edital_agent),
) -> DossieEdital:
    """Análise on-demand do edital + matrícula de um lote (dossiê jurídico via LLM)."""
    return DossieEdital(**agent.analisar(req.link))


def _avaliar_imovel(
    imovel: ImovelPreview,
    tools: AuctionTools,
    engine_market: MarketValuationEngine,
    engine_itbi: ValuationEngineITBI,
) -> ImovelPreview:
    """Avalia um lote: valor de MERCADO (base do ROI) + PISO ITBI (faixa).

    Isolado da rota para ser reutilizado tanto pela varredura em lote quanto pela
    versão em streaming, sem duplicar a lógica de negócio.
    """
    geo = tools.get_geo_location(imovel.district)
    lat, lon = geo.get("lat", -23.5505), geo.get("lon", -46.6333)

    imovel.ml_predicted_price = engine_market.predict_price(imovel, lat, lon)
    imovel.roi_potential = roi_potencial(imovel.ml_predicted_price, imovel.auction_price)

    # Piso ITBI (faixa — não mexe no ROI). Só busca o SQL (1 HTTP por imóvel) se
    # há índice cadastral pra casar; sem índice, o piso usa o tier geo pela coord.
    try:
        imovel.cadastral_sql = tools.fetch_cadastral_sql(imovel.link) if engine_itbi.iptu else None
        res = engine_itbi.predict(imovel.cadastral_sql, imovel.area_m2, lat, lon)
        if res.get("servable"):
            imovel.itbi_price = res["price"]
            imovel.valuation_tier = res["tier"]
    except Exception as e:
        logger.warning("ITBI falhou para '%s': %s", imovel.title, e)

    return imovel


@router.post(
    "/varredura",
    response_model=list[ImovelPreview],
    name="analise:realizar_varredura",
)
def realizar_varredura_e_predicao(
    request: AnaliseRequest,
    db: Session = Depends(get_db),
    tools: AuctionTools = Depends(get_tools),
    engine_market: MarketValuationEngine = Depends(get_engine_market),
    engine_itbi: ValuationEngineITBI = Depends(get_engine_itbi),
) -> list[ImovelPreview]:

    start_time = time.time()

    try:
        # 1. Scraping Inicial
        imoveis_raw = tools.fetch_listings(request.url)

        if not imoveis_raw:
            raise HTTPException(status_code=404, detail="Nenhum imóvel extraído.")

        # 2. Inferência ML por imóvel (valor de mercado v3 + piso ITBI).
        #    A avaliação de cada lote está isolada em `_avaliar_imovel`, reutilizada
        #    também pela versão em streaming (/varredura/stream).
        resultados = [
            _avaliar_imovel(imovel, tools, engine_market, engine_itbi)
            for imovel in imoveis_raw
        ]

        # Ordenação por ROI
        resultados.sort(key=lambda x: x.roi_potential or 0.0, reverse=True)

        # Log de auditoria
        tempo_total = time.time() - start_time
        log = models.AuditLog(
            target_url=request.url,
            total_properties=len(resultados),
            execution_time_sec=round(tempo_total, 2),
            success_rate=100.0 # Sucesso total se chegou aqui
        )
        db.add(log)
        db.commit()

        return resultados

    except Exception as e:
        db.rollback() # Garante que erros não deixem transações abertas
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/varredura/stream", name="analise:varredura_stream")
def realizar_varredura_stream(
    request: AnaliseRequest,
    db: Session = Depends(get_db),
    tools: AuctionTools = Depends(get_tools),
    engine_market: MarketValuationEngine = Depends(get_engine_market),
    engine_itbi: ValuationEngineITBI = Depends(get_engine_itbi),
) -> StreamingResponse:
    """Varredura PROGRESSIVA: emite cada lote (NDJSON) assim que é avaliado.

    Em vez de esperar toda a varredura (60–90s) para devolver a lista de uma vez,
    o front recebe uma linha JSON por evento e vai montando os cards conforme
    chegam. Eventos: status | total | item | done | error.
    """
    def eventos():
        start = time.time()
        yield json.dumps({"type": "status", "phase": "scraping"}) + "\n"

        try:
            imoveis_raw = tools.fetch_listings(request.url)
        except Exception as e:
            yield json.dumps({"type": "error", "detail": f"Falha ao varrer: {e}"}) + "\n"
            return
        if not imoveis_raw:
            yield json.dumps({"type": "error", "detail": "Nenhum imóvel extraído."}) + "\n"
            return

        yield json.dumps({"type": "total", "total": len(imoveis_raw)}) + "\n"

        avaliados = 0
        for imovel in imoveis_raw:
            try:
                _avaliar_imovel(imovel, tools, engine_market, engine_itbi)
            except Exception as e:
                logger.warning("Avaliação falhou para '%s': %s", imovel.title, e)
            avaliados += 1
            yield json.dumps({"type": "item", "imovel": imovel.model_dump()}, default=str) + "\n"

        # Log de auditoria (mesma telemetria da versão em lote).
        try:
            db.add(models.AuditLog(
                target_url=request.url,
                total_properties=avaliados,
                execution_time_sec=round(time.time() - start, 2),
                success_rate=100.0,
            ))
            db.commit()
        except Exception:
            db.rollback()

        yield json.dumps({"type": "done", "total": avaliados}) + "\n"

    # X-Accel-Buffering: no ajuda a não bufferizar atrás de proxies (nginx).
    return StreamingResponse(
        eventos(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )