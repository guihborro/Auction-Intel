"""Configurações globais, lidas do ambiente e do arquivo `.env`."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# src/auction_intel/config.py -> raiz do repositório
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configurações da aplicação. Todas podem ser sobrescritas no `.env`."""

    PROJECT_NAME: str = "Auction Intel API"
    VERSION: str = "1.0.0"

    # Banco de dados: SQLite local por padrão. Para PostgreSQL (por exemplo AWS RDS),
    # defina DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco
    DATABASE_URL: str = "sqlite:///./sql_app.db"

    # Pastas de artefatos (modelos treinados, índices de dados e o site estático)
    MODELS_DIR: Path = REPO_ROOT / "models"
    DATASETS_DIR: Path = REPO_ROOT / "datasets"
    WEB_DIR: Path = REPO_ROOT / "web"

    # LLM para análise do edital: provider-agnóstico (endpoint compatível com OpenAI).
    # Padrão: Google Gemini Flash (camada gratuita). Troque no .env para outro provedor.
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_MODEL: str = "gemini-2.0-flash"

    # Coleta
    HEADLESS_BROWSER: bool = True
    VARREDURA_MAX_PAGES: int = 5  # em ambientes leves, use 1

    # Motor
    MARGEM_LUCRO_MINIMA: float = 0.20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
