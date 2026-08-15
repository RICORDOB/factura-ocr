"""FastAPI principal: sirve el frontend y expone la API de extracción/guardado."""
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, excel
from app.extractor import validate
from app.ocr import extract_invoice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Factura → Excel", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    """Sirve la landing/UI de carga de facturas."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)) -> JSONResponse:
    """Recibe JPG/PNG/PDF, extrae los datos de la factura y los devuelve
    para que el usuario los confirme o corrija antes de guardar."""
    filename = file.filename or "archivo"
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Formato no soportado ({ext}). Usa JPG, PNG o PDF.",
        )

    content = await file.read()
    if len(content) > config.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="El archivo supera los 15 MB (límite de procesamiento).",
        )

    try:
        data = extract_invoice(content, filename)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error al procesar la factura")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo procesar la factura: {exc}",
        ) from exc

    return JSONResponse({"ok": True, "archivo": filename, "datos": data})


@app.post("/api/save")
async def save(payload: dict) -> JSONResponse:
    """Recibe los datos confirmados (o corregidos) y los agrega al Excel."""
    datos = payload.get("datos")
    if not isinstance(datos, dict):
        raise HTTPException(status_code=400, detail="Faltan los datos de la factura.")

    errores, limpio = validate(datos)
    if errores:
        return JSONResponse({"ok": False, "errores": errores}, status_code=422)

    try:
        resultado = excel.append_invoice(config.EXCEL_PATH, limpio)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error al guardar en Excel")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo guardar en Excel: {exc}",
        ) from exc

    return JSONResponse({"ok": True, **resultado})


@app.get("/api/download")
def download():
    """Descarga el archivo Excel actual (útil para respaldar la base de datos)."""
    path = Path(config.EXCEL_PATH)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Aún no hay facturas guardadas.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )
