from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BASE_DIR / "storage" / "files"
OCR_TMP_DIR = STORAGE_DIR / "ocr_tmp"
INBOX_DIR = STORAGE_DIR / "inbox"
PENDIENTES_CLASIFICADOS_DIR = STORAGE_DIR / "pendientes_clasificados"
NO_IDENTIFICADOS_DIR = STORAGE_DIR / "no_identificados"
ERROR_DIR = STORAGE_DIR / "error"

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "gestiondocumental")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres123")