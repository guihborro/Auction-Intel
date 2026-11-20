"""Configuração comum dos testes.

Aponta o banco para um SQLite temporário antes de qualquer import da aplicação,
para que os testes não criem `sql_app.db` dentro do repositório.
"""

import os
import tempfile
from pathlib import Path

_DB = Path(tempfile.gettempdir()) / "auction_intel_test.db"
_DB.unlink(missing_ok=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB}")
