import logging
import sys

# Garante saída em UTF-8 mesmo em consoles legados (Windows cp1252), evitando que
# um print com emoji nos logs derrube uma requisição (UnicodeEncodeError).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from auction_intel.api.router import api_router  # noqa: E402
from auction_intel.config import settings  # noqa: E402
from auction_intel.db import models  # noqa: E402
from auction_intel.db.database import engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Cria as tabelas se elas não existirem
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Auction Intel API",
    description="Coleta, valor justo com machine learning e leitura de edital para leilões de imóveis.",
    version=settings.VERSION,
)

# CORS: o site é servido na mesma origem; a liberação ampla atende clientes externos da API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

# Frontend estático (SPA) servido na raiz, na mesma origem da API.
# Montado por último para que /api/v1/* tenha precedência sobre os arquivos.
if settings.WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=settings.WEB_DIR, html=True), name="web")
