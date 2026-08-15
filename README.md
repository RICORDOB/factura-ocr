# Factura → Excel

Aplicación web que extrae los datos más importantes de una factura colombiana a partir de una imagen o PDF y los agrega a una base de datos Excel (`.xlsx`). El archivo Excel se crea en la primera carga y en adelante **solo se agregan filas**; nunca se sobrescribe.

## Stack
- **Backend**: FastAPI (Python)
- **Frontend**: HTML/CSS/JS (diseño responsivo)
- **OCR**: Google Document AI (`Invoice Processor`) — con modo **mock** para desarrollo sin API
- **Excel**: openpyxl (hoja `Facturas` + hoja `Detalles` con los productos de cada factura)
- **Despliegue**: Docker + Render

## Estructura
```
factura-ocr/
├── requirements.txt
├── .env.example        # plantilla de configuración
├── Dockerfile          # imagen para Render / Docker
├── render.yaml         # blueprint de Render
├── app/
│   ├── main.py         # FastAPI: endpoints
│   ├── config.py       # variables de entorno
│   ├── ocr.py          # Google Document AI + Mock
│   ├── extractor.py    # normalización y validación
│   ├── excel.py        # crear/append en .xlsx (2 hojas)
│   └── static/         # index.html, style.css, app.js
└── data/
    └── base_facturas.xlsx  # se genera en la primera carga
```

## Endpoints
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Interfaz web |
| POST | `/api/extract` | Sube JPG/PNG/PDF y devuelve datos extraídos para revisión |
| POST | `/api/save` | Guarda datos confirmados en el Excel (cabecera + productos) |
| GET | `/api/download` | Descarga el Excel actual (respaldo) |

## Puesta en marcha (modo mock, sin API)
```bash
cd ~/Desktop/factura-ocr
cp .env.example .env
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
# Abre http://127.0.0.1:8000
```
Con `OCR_MODE=mock` la app devuelve datos de ejemplo: el flujo web → Excel funciona sin credenciales.

## Conectar Google Document AI (OCR real)
1. En [Google Cloud Console](https://console.cloud.google.com) crea un proyecto y activa la API **Document AI**.
2. Ve a **Document AI → Processors → Create processor** y crea uno tipo **Invoice Processor** (location `us`). Copia el **Processor ID**.
3. Crea una **service account**, asígnale el rol con permisos de Document AI y descarga su clave JSON.
4. Edita `.env`:
```bash
OCR_MODE=google
GOOGLE_APPLICATION_CREDENTIALS=/ruta/a/clave.json
DOCUMENT_AI_PROJECT_ID=tu-proyecto
DOCUMENT_AI_LOCATION=us
DOCUMENT_AI_PROCESSOR_ID=tu-processor-id
```
5. Reinicia el servidor. El procesador se cobra por página procesada.

## Campos extraídos
### Hoja `Facturas` (una fila por factura)
| Excel | Fuente (Document AI) |
|---|---|
| Fecha | `invoice_date` |
| NIT | `seller_tax_id` |
| Razón social | `seller_name` |
| N° Factura | `invoice_id` |
| Subtotal | `total_net_amount` |
| IVA | `total_tax_amount` |
| Total | `total_amount` |
| Moneda | `currency` |

### Hoja `Detalles` (una fila por producto, vinculada por N° Factura)
| Excel | Fuente (Document AI) |
|---|---|
| N° Factura | `invoice_id` (vínculo) |
| Producto | `line_item/description` |
| Cantidad | `line_item/quantity` |
| Precio Unitario | `line_item/unit_price` |
| Subtotal | `line_item/amount` |
| IVA | `line_item/tax_amount` |
| Total | subtotal + IVA |

## Despliegue en Render (plan free)
1. Sube el repo a GitHub (el `render.yaml` y `Dockerfile` ya están configurados).
2. En [render.com](https://render.com) → **New → Blueprint** → conéctalo al repo.
3. Render crea el web service automáticamente (Docker, plan free).

**Nota sobre el health check**: Render verifica la salud del servicio con `HEAD /`. La app responde 200 en `app/main.py` (`@app.head("/")`); sin eso Render derriba el servicio al fallar el check.

**Importante (plan free de Render)**: el sistema de archivos es efímero — el Excel se pierde al reiniciar/redeployear. Usa el botón **Descargar Excel actual** en la web para respaldar tus datos regularmente, o conecta un disco persistente (plan de pago). La data vive en `data/base_facturas.xlsx`.

## Notas
- Límite de archivo: 15 MB (inline de Document AI). Para archivos mayores se necesita Google Cloud Storage.
- Formatos: JPG, PNG, PDF.
- El usuario confirma/corrige los datos extraídos (incluidos los productos) antes de guardar en Excel.
