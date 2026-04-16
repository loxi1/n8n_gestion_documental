from __future__ import annotations

import re
from typing import Any


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def detect_document_type(text: str, original_name: str) -> str:
    text_u = text.upper()
    name_u = original_name.upper()

    if "FACTURA" in text_u or re.search(r"\bF[A-Z0-9]{2,4}[- ]?\d{3,}\b", text_u):
        return "factura"
    if "NOTA DE CRÉDITO" in text_u or "NOTA DE CREDITO" in text_u or "NC" in name_u:
        return "nota_credito"
    if "GUÍA DE REMISIÓN" in text_u or "GUIA DE REMISION" in text_u or "GUIA" in name_u:
        return "guia"
    if "ORDEN DE COMPRA" in text_u or "ORDEN DE COMRA" in text_u or "OC" in name_u:
        return "orden_compra"

    return "otro"


def extract_basic_fields(text: str, original_name: str) -> dict[str, Any]:
    text_u = text.upper()

    doc_type = detect_document_type(text, original_name)

    ruc = _search(r"\bRUC[:\s]*([0-9]{11})\b", text_u)
    if not ruc:
        ruc = _search(r"\b([0-9]{11})\b", text_u)

    serie_numero = None
    for pattern in [
        r"\b([FBET]\d{3}[- ]\d{3,})\b",
        r"\b([A-Z0-9]{3,5}[- ]\d{3,})\b",
    ]:
        serie_numero = _search(pattern, text_u)
        if serie_numero:
            break

    serie = None
    numero = None
    if serie_numero and "-" in serie_numero:
        parts = [p.strip() for p in serie_numero.replace(" ", "").split("-", 1)]
        if len(parts) == 2:
            serie, numero = parts

    fecha_emision = _search(r"\bFECHA(?: DE EMISI[ÓO]N)?[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})\b", text_u)

    importe = _search(
        r"\b(?:IMPORTE TOTAL|TOTAL A PAGAR|TOTAL)[:\sS/]*([0-9]+(?:[.,][0-9]{2})?)\b",
        text_u,
    )

    return {
        "tipo_documental": doc_type,
        "ruc": ruc,
        "serie": serie,
        "numero": numero,
        "fecha_emision": fecha_emision,
        "importe": importe,
    }