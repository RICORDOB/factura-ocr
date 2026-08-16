"""Motor OCR de la aplicación.

Expone una única interfaz: `extract(file_bytes, filename) -> dict de entidades`.

- `MockOCR`: devuelve datos de ejemplo de una factura colombiana. Sirve para
  probar todo el flujo (web -> extracción -> Excel) sin depender de Google Cloud.
- `GoogleDocumentAI`: llama al procesador pre-entrenado "Invoice Processor" de
  Google Document AI. Se activa con OCR_MODE=google y credenciales en .env.

`build_ocr()` instancia el motor correcto según la configuración.
"""
from __future__ import annotations

import hashlib

from app import config
from app.extractor import normalize

# Estructura de factura colombiana de ejemplo para el mock
_MOCK_FACTURA = {
    "invoice_date": "2026-08-15",
    "seller_tax_id": "900123456-7",
    "seller_name": "DISTRIBUCIONES DEL VALLE S.A.S.",
    "invoice_id": "SETP 00012345",
    "total_net_amount": 100000.00,
    "total_tax_amount": 19000.00,
    "total_amount": 119000.00,
    "currency": "COP",
}

# Productos de ejemplo para el mock (misma estructura que el GoogleDocumentAI)
_MOCK_LINE_ITEMS = [
    {
        "description": "Arroz blanco premium 1kg",
        "quantity": 10,
        "unit_price": 4200.00,
        "amount": 42000.00,
        "tax_amount": 7980.00,
        "product_code": "4532",
    },
    {
        "description": "Aceite vegetal 900ml",
        "quantity": 4,
        "unit_price": 14500.00,
        "amount": 58000.00,
        "tax_amount": 11020.00,
        "product_code": "9876",
    },
]


class MockOCR:
    """OCR de prueba que no requiere ningún servicio externo."""

    def extract(self, file_bytes: bytes, filename: str) -> dict:
        """Simula la extracción. Varía los montos según el hash del archivo para
        que cada carga genere un registro distinto."""
        digest = hashlib.sha256(file_bytes).hexdigest()
        variante = int(digest[:4], 16) % 1000

        entities = dict(_MOCK_FACTURA)
        entities["total_amount"] = round(119000 + variante, 2)
        entities["total_net_amount"] = round(100000 + variante, 2)
        entities["total_tax_amount"] = round((entities["total_net_amount"]) * 0.19, 2)
        entities["invoice_id"] = f"SETP {100000 + variante:06d}"

        # Los productos del mock se replican con los montos variados
        scale = 1 + variante / 100000
        line_items = []
        for item in _MOCK_LINE_ITEMS:
            item_variant = dict(item)
            item_variant["unit_price"] = round(item["unit_price"] * scale, 2)
            item_variant["amount"] = round(item["amount"] * scale, 2)
            item_variant["tax_amount"] = round(item["tax_amount"] * scale, 2)
            line_items.append(item_variant)
        entities["line_items"] = line_items
        return entities


class GoogleDocumentAI:
    """Integración con el Invoice Processor de Google Document AI."""

    def __init__(self) -> None:
        try:
            from google.cloud import documentai_v1 as documentai
        except ImportError:
            raise RuntimeError(
                "Falta la librería google-cloud-documentai. Instálala con: "
                "pip install google-cloud-documentai"
            ) from None

        self._documentai = documentai
        self.client = documentai.DocumentProcessorServiceClient()
        self.processor_name = self.client.processor_path(
            config.DOCUMENT_AI_PROJECT_ID,
            config.DOCUMENT_AI_LOCATION,
            config.DOCUMENT_AI_PROCESSOR_ID,
        )

    def extract(self, file_bytes: bytes, filename: str) -> dict:
        """Envía el documento inline al procesador y devuelve las entidades."""
        document = self._documentai.types.RawDocument(
            content=file_bytes,
            mime_type=self._guess_mime(filename),
        )
        request = self._documentai.types.ProcessRequest(
            name=self.processor_name,
            raw_document=document,
        )
        result = self.client.process_document(request=request)

        entities: dict = {}
        line_items: list[dict] = []
        for entity in result.document.entities:
            key = entity.type_.strip()

            # Los ítems de factura llegan como entidad "line_item" con sub-entidades
            if key == "line_item":
                item = self._parse_line_item(entity)
                if item:
                    line_items.append(item)
                continue

            value = self._entity_text(entity)
            if value and value.strip():
                # Se conserva la primera aparición de cada tipo de entidad
                entities.setdefault(key, value.strip())

        if line_items:
            entities["line_items"] = line_items
        return entities

    def _parse_line_item(self, entity) -> dict:
        """Convierte una entidad 'line_item' de Document AI en un dict simple.

        Las propiedades típicas son line_item/description, line_item/quantity,
        line_item/unit_price, line_item/amount, line_item/tax_amount y
        line_item/product_code.
        """
        item: dict = {}
        for prop in entity.properties:
            prop_key = prop.type_.replace("line_item/", "").strip()
            value = self._entity_text(prop)
            if value and value.strip():
                item.setdefault(prop_key, value.strip())
        return item if item else None

    @staticmethod
    def _entity_text(entity) -> str:
        """Extrae el texto de una entidad tolerando las versiones del SDK.

        En google-cloud-documentai >= 3.x los valores están en `mention_text`
        (con normalizado en `normalized_value.text`); en versiones previas era
        `text_value` / `text`.
        """
        normalized = getattr(entity, "normalized_value", None)
        if normalized and getattr(normalized, "text", None):
            return normalized.text
        text_value = getattr(entity, "text_value", "")
        if text_value:
            return text_value
        text = getattr(entity, "mention_text", "")
        if text is None:
            text = getattr(entity, "text", "")
        return text

    @staticmethod
    def _guess_mime(filename: str) -> str:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return "application/pdf"
        if lower.endswith((".png")):
            return "image/png"
        if lower.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        return "application/octet-stream"


def build_ocr():
    """Instancia el motor OCR correspondiente a OCR_MODE."""
    if config.OCR_MODE == "google":
        return GoogleDocumentAI()
    return MockOCR()


def extract_invoice(file_bytes: bytes, filename: str) -> dict:
    """Punto de entrada único: devuelve los datos normalizados de la factura."""
    ocr = build_ocr()
    raw_entities = ocr.extract(file_bytes, filename)
    return normalize(raw_entities)
