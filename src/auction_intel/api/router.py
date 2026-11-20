from fastapi import APIRouter
from auction_intel.api.routes import health, analise, watchlist, auth

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(analise.router, prefix="/leiloes", tags=["Motor Preditivo"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])
api_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])