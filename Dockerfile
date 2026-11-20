# Auction Intel — imagem para Hugging Face Spaces (Docker) e execução local.
# Sobe a API FastAPI, que também serve o site (web/), numa porta só.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HEADLESS_BROWSER=True

# Dependências de sistema + uv (como root)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

# Dependências Python (camada de cache: só refaz se pyproject/lock mudarem).
# --no-dev: sem pytest/ruff na imagem de produção.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Chromium + bibliotecas de sistema do navegador, num caminho legível por todos
RUN uv run playwright install --with-deps chromium \
    && chmod -R a+rx /ms-playwright

# Código, modelos treinados e site
COPY src ./src
COPY models ./models
COPY web ./web
RUN uv sync --frozen --no-dev

# Usuário não-root (exigência do Hugging Face Spaces); dono do /app para venv e SQLite
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

# O HF Spaces expõe a porta declarada em `app_port` (7860) no README do Space.
EXPOSE 7860
CMD ["uv", "run", "--no-sync", "uvicorn", "auction_intel.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
