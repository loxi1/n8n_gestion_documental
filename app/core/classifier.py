from __future__ import annotations

import re
from typing import Any


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def detect_document_type(text: str, original_name: str) -> str:
    text_u = text.upper()
    name_u = original_name.upper()

    if (
        "FACTURA ELECTRÓNICA" in text_u
        or "FACTURA ELECTRONICA" in text_u
        or "FACTURA" in text_u
        or re.search(r"\bF[0-9A-Z]{2,4}-\d{3,}\b", text_u)
    ):
        return "factura"

    if (
        "GUÍA DE REMISIÓN" in text_u
        or "GUIA DE REMISION" in text_u
        or "GUÍA DE REMISION" in text_u
        or "GUIA DE REMISIÓN" in text_u
        or "GUIA" in name_u
    ):
        return "guia"

    if (
        "ORDEN DE COMPRA" in text_u
        or "ORDEN DE COMRA" in text_u
        or "ORDEN DE COMPRA" in name_u
        or "ORDEN DE COMRA" in name_u
        or re.search(r"\bOC\b", text_u)
    ):
        return "orden_compra"

    if (
        "NOTA DE CREDITO" in text_u
        or "NOTA DE CRÉDITO" in text_u
        or "NOTA DE DEBITO" in text_u
        or "NOTA DE DÉBITO" in text_u
    ):
        return "nota"

    return "otro"


def extract_basic_fields(text: str, original_name: str) -> dict[str, Any]:
    text_u = text.upper()

    doc_type = detect_document_type(text, original_name)

    ruc = _search(r"\bRUC[:\s]*([0-9]{11})\b", text_u)
    if not ruc:
        ruc = _search(r"\b([0-9]{11})\b", text_u)

    serie = None
    numero = None

    patrones_doc = [
        r"\bNRO\.?\s*([A-Z0-9]{3,5})[- ]([0-9]{3,})\b",
        r"\bN[°º]\s*([A-Z0-9]{3,5})[- ]([0-9]{3,})\b",
        r"\b([A-Z0-9]{3,5})[- ]([0-9]{3,})\b",
    ]

    for patron in patrones_doc:
        match = re.search(patron, text_u, re.IGNORECASE)
        if match:
            serie = match.group(1).strip()
            numero = match.group(2).strip()
            break

    fecha_emision = _search(
        r"\bFECHA(?: DE EMISI[ÓO]N)?[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})\b",
        text_u
    )
    if not fecha_emision:
        fecha_emision = _search(
            r"\b([0-9]{2}-[A-Z]{3}-[0-9]{4})\b",
            text_u
        )

    importe = _search(
        r"\b(?:TOTAL|NETO A PAGAR|TOTAL S/|TOTAL USD \$|TOTAL \(USD \$\))[:\sS/$]*([0-9]+(?:[.,][0-9]{2})?)\b",
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