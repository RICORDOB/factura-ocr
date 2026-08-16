"""Normalización de los datos crudos del OCR a un dict canónico de factura colombiana.

Tanto el OCR real (Google Document AI) como el mock devuelven un dict con las
entidades detectadas; aquí se unifica a los campos que consumen Excel y frontend.

Formato de salida esperado:
{
    "fecha": "2026-08-15",
    "nit": "900123456-7",
    "razon_social": "...",
    "numero_factura": "SETP 00012345",
    "subtotal": 100.00,
    "iva": 19.00,
    "total": 119.00,
    "moneda": "COP",
    "line_items": [
        {
            "producto": "Arroz 1kg",
            "cantidad": 10,
            "precio_unitario": 4200.00,
            "subtotal": 42000.00,
            "iva": 7980.00,
            "total": 49980.00,
        },
    ],
}
"""
from typing import Any

# Sinónimos por los que Document AI puede nombrar cada campo, según versión del API
_FIELD_ALIASES = {
    "fecha": ["invoice_date", "fecha", "date"],
    "nit": ["seller_tax_id", "supplier_tax_id", "tax_id", "nit", "rut"],
    "razon_social": ["seller_name", "supplier_name", "razon_social", "name"],
    "numero_factura": ["invoice_id", "numero_factura", "invoice_number", "document_id"],
    "subtotal": ["total_net_amount", "net_amount", "subtotal", "total_net"],
    "iva": ["total_tax_amount", "tax_amount", "vat", "iva"],
    "total": ["total_amount", "total", "grand_total"],
    "moneda": ["currency", "moneda"],
}


def _first_value(raw: dict, keys: list[str]) -> Any:
    """Devuelve el primer valor no vacío hallado en raw usando los alias dados."""
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "None"):
            return value
    return None


def _as_number(value: Any) -> float | None:
    """Convierte a float tolerando formatos de montos latinoamericanos.

    Reglas (montos de factura):
    - Se quitan símbolos de moneda y espacios.
    - La coma o el punto usado como separador de miles (bloque de 3 dígitos)
      se elimina; el último separador con 1-2 dígitos es el decimal.
      Ej.: "119,000" -> 119000.0 · "4,200" -> 4200.0 · "14.500" -> 14500.0
           "1.234.567,89" -> 1234567.89 · "14.5" -> 14.5
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace("COP", "").replace(" ", "")
    try:
        numero = float(text)
    except ValueError:
        numero = None

    if numero is not None:
        # float() acepta "833.835" y "166767", pero en formatos COP el punto o la
        # coma seguidos de 3 dígitos son separador de miles: "833.835" -> 833835.0
        last_sep = max(text.rfind(","), text.rfind("."))
        if last_sep > 0 and len(text) - last_sep - 1 >= 3:
            try:
                return float(text.replace(",", "").replace(".", ""))
            except ValueError:
                pass
        return numero

    # Si no hay separadores, ya falló: no es numérico
    if "," not in text and "." not in text:
        return None

    # Contar dígitos después del último separador
    last_sep = max(text.rfind(","), text.rfind("."))
    decimals = len(text) - last_sep - 1

    if decimals == 3:
        # El separador final es de miles: no hay decimales
        candidate = text.replace(",", "").replace(".", "")
    else:
        # El último separador es decimal (1-2 dígitos); los anteriores son miles
        integer_part, _, frac_part = text.rpartition(text[last_sep])
        candidate = integer_part.replace(",", "").replace(".", "") + "." + frac_part

    try:
        return float(candidate)
    except ValueError:
        return None


def _rounded(value: Any) -> float | None:
    """Redondea un monto a 2 decimales; devuelve None si no es numérico."""
    numero = _as_number(value)
    if numero is None:
        return None
    return round(numero, 2)


def normalize(raw_entities: dict) -> dict:
    """Convierte entidades crudas del OCR en el dict canónico de factura."""
    fecha = _first_value(raw_entities, _FIELD_ALIASES["fecha"])
    nit = _first_value(raw_entities, _FIELD_ALIASES["nit"])
    razon_social = _first_value(raw_entities, _FIELD_ALIASES["razon_social"])
    numero_factura = _first_value(raw_entities, _FIELD_ALIASES["numero_factura"])
    subtotal = _rounded(_first_value(raw_entities, _FIELD_ALIASES["subtotal"]))
    iva = _rounded(_first_value(raw_entities, _FIELD_ALIASES["iva"]))
    total = _rounded(_first_value(raw_entities, _FIELD_ALIASES["total"]))
    moneda = _first_value(raw_entities, _FIELD_ALIASES["moneda"]) or "COP"

    return {
        "fecha": str(fecha) if fecha else "",
        "nit": str(nit).strip() if nit else "",
        "razon_social": str(razon_social).strip() if razon_social else "",
        "numero_factura": str(numero_factura).strip() if numero_factura else "",
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
        "moneda": str(moneda).strip().upper() if moneda else "COP",
        "line_items": _normalize_line_items(raw_entities.get("line_items")),
    }


# Alias de las sub-entidades de Document AI para cada campo de línea
_LINE_ALIASES = {
    "producto": ["description", "descripcion", "product", "name", "product_code"],
    "cantidad": ["quantity", "cantidad", "qty"],
    "precio_unitario": ["unit_price", "precio_unitario", "unitprice"],
    "subtotal": ["amount", "subtotal", "line_amount", "item_amount"],
    "iva": ["tax_amount", "iva", "tax"],
}


def _normalize_line_items(raw_items: Any) -> list[dict]:
    """Convierte los line_items crudos (Document AI o mock) en el formato canónico."""
    if not isinstance(raw_items, list):
        return []
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = {
            "producto": str(_first_value(raw, _LINE_ALIASES["producto"]) or "").strip(),
            "cantidad": _rounded(_first_value(raw, _LINE_ALIASES["cantidad"])),
            "precio_unitario": _rounded(_first_value(raw, _LINE_ALIASES["precio_unitario"])),
            "subtotal": _rounded(_first_value(raw, _LINE_ALIASES["subtotal"])),
            "iva": _rounded(_first_value(raw, _LINE_ALIASES["iva"])),
        }
        if not item["producto"] and item["subtotal"] is None:
            continue  # línea vacía, se descarta
        items.append(item)
    return items


def validate(data: dict) -> tuple[list[str], dict]:
    """Valida los datos normalizados antes de guardar.

    Devuelve (errores, datos_limpios). Si errores está vacío, es seguro guardar.
    """
    errores: list[str] = []
    limpio = dict(data)

    fecha = str(data.get("fecha") or "").strip()
    if not fecha:
        errores.append("La fecha es obligatoria.")

    nit = str(data.get("nit") or "").strip()
    if not nit:
        errores.append("El NIT es obligatorio.")
    elif len(nit.replace("-", "").replace(".", "")) < 8:
        errores.append("El NIT parece incompleto (mínimo 8 dígitos).")
    limpio["nit"] = nit

    if not str(data.get("razon_social") or "").strip():
        errores.append("La razón social es obligatoria.")

    if not str(data.get("numero_factura") or "").strip():
        errores.append("El número de factura es obligatorio.")

    for campo in ("subtotal", "iva", "total"):
        valor = data.get(campo)
        if valor is None or (isinstance(valor, float) and valor < 0):
            limpio[campo] = 0.0
        else:
            try:
                limpio[campo] = round(float(valor), 2)
            except (TypeError, ValueError):
                limpio[campo] = 0.0

    if limpio["total"] == 0:
        errores.append("El total es obligatorio y no puede ser cero.")

    # Line items: se conservan solo las líneas con producto o monto
    limpio["line_items"] = []
    for raw in data.get("line_items") or []:
        if not isinstance(raw, dict):
            continue
        producto = str(raw.get("producto") or "").strip()
        cantidad = _as_number(raw.get("cantidad")) or 0.0
        precio = _as_number(raw.get("precio_unitario")) or 0.0
        subtotal = _as_number(raw.get("subtotal"))
        iva = _as_number(raw.get("iva"))
        total_linea = _as_number(raw.get("total"))

        if not producto and subtotal is None:
            continue

        if subtotal is None:
            subtotal = round(cantidad * precio, 2)
        if total_linea is None:
            total_linea = round((subtotal or 0) + (iva or 0), 2)

        limpio["line_items"].append(
            {
                "producto": producto,
                "cantidad": round(cantidad, 2),
                "precio_unitario": round(precio, 2),
                "subtotal": round(subtotal, 2),
                "iva": round(iva, 2) if iva is not None else None,
                "total": round(total_linea, 2),
            }
        )

    return errores, limpio
