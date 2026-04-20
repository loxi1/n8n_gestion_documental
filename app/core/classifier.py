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
        "ORDEN DE COMPRA" in text_u
        or "ORDEN DE COMRA" in text_u
        or "ORDEN DE COMPRA" in name_u
        or "ORDEN DE COMRA" in name_u
    ):
        return "orden_compra"

    if (
        "REQUERIMIENTO DE COMPRA" in text_u
        or "REQUERIMIENTO" in text_u
        or "REQ" in name_u
    ):
        return "requerimiento_compra"

    if (
        "GUIA DE REMISION" in text_u
        or "GUÍA DE REMISIÓN" in text_u
        or "GUIA DE REMISION ELECTRONICA" in text_u
        or "GUÍA DE REMISIÓN ELECTRÓNICA" in text_u
        or "PUNTO DE PARTIDA" in text_u
        or "PUNTO DE LLEGADA" in text_u
    ):
        return "guia"

    if (
        "FACTURA ELECTRONICA" in text_u
        or "FACTURA ELECTRÓNICA" in text_u
        or re.search(r"\bF\d{3,4}-\d{3,}\b", text_u)
    ):
        return "factura"

    if (
        "NOTA DE CREDITO" in text_u
        or "NOTA DE CRÉDITO" in text_u
        or "NOTA DE DEBITO" in text_u
        or "NOTA DE DÉBITO" in text_u
    ):
        return "nota_credito"

    return "otro"


def extract_basic_fields(text: str, original_name: str) -> dict[str, Any]:
    text_u = text.upper()
    doc_type = detect_document_type(text, original_name)

    ruc = _search(r"\bRUC[:\s]*([0-9]{11})\b", text_u)
    if not ruc:
        ruc = _search(r"\b([0-9]{11})\b", text_u)

    serie = None
    numero = None
    oc = None

    if doc_type == "factura":
        patrones = [r"\b(F\d{3,4})[- ]([0-9]{3,})\b"]
    elif doc_type == "guia":
        patrones = [
            r"\b(TO?\d{3,4})[- ]([0-9]{3,})\b",
        ]
    elif doc_type == "orden_compra":
        patrones = [
            r"\bORDEN DE COMPRA\s*N[^0-9]{0,5}([0-9]{3,})\b",
            r"\bOC[:\s]*([0-9]{3,})\b",
        ]
    elif doc_type == "requerimiento_compra":
        patrones = [
            r"\bRC[:\s-]*([0-9]{3,})\b",
            r"\bREQ[:\s-]*([0-9]{3,})\b",
        ]
    else:
        patrones = []

    for patron in patrones:
        m = re.search(patron, text_u, re.IGNORECASE)
        if m:
            if doc_type == "factura":
                serie = m.group(1).strip()
                numero = m.group(2).strip()
            elif doc_type == "guia":
                serie = m.group(1).strip()
                numero = m.group(2).strip()
                serie = serie.replace("TO", "T", 1)
            elif doc_type == "orden_compra":
                serie = "OC"
                numero = m.group(1).strip()
            elif doc_type == "requerimiento_compra":
                serie = "REQ"
                numero = m.group(1).strip()
            break

    oc_match = re.search(r"\bOC[:\s]*([0-9]{3,})\b", text_u, re.IGNORECASE)
    if oc_match:
        oc = oc_match.group(1).strip()

    fecha_emision = _search(
        r"\bFECHA(?: DE EMISION| DE EMISIÓN)?[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})\b",
        text_u
    )
    if not fecha_emision:
        fecha_emision = _search(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b", text_u)
    if not fecha_emision:
        fecha_emision = _search(r"\b([0-9]{2}-[A-Z]{3}-[0-9]{4})\b", text_u)

    importe = _search(
        r"\b(?:TOTAL|TOTAL S/|TOTAL USD \$|TOTAL \(USD \$\))[:\sS/$]*([0-9]+(?:[.,][0-9]{2})?)\b",
        text_u,
    )

    return {
        "tipo_documental": doc_type,
        "ruc": ruc,
        "serie": serie,
        "numero": numero,
        "fecha_emision": fecha_emision,
        "importe": importe,
        "oc": oc,
    }