"""Configuración central de la aplicación. Lee las variables desde .env y las expone."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _path(value: str) -> Path:
    """Convierte una ruta del .env en Path, resolviéndola contra la raíz del proyecto
    si no es absoluta."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else BASE_DIR / p


OCR_MODE = os.getenv("OCR_MODE", "mock").strip().lower()

GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
DOCUMENT_AI_PROJECT_ID = os.getenv("DOCUMENT_AI_PROJECT_ID", "")
DOCUMENT_AI_LOCATION = os.getenv("DOCUMENT_AI_LOCATION", "us")
DOCUMENT_AI_PROCESSOR_ID = os.getenv("DOCUMENT_AI_PROCESSOR_ID", "")

EXCEL_PATH = _path(os.getenv("EXCEL_PATH", "./data/base_facturas.xlsx"))
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB, límite inline de Document AI

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
