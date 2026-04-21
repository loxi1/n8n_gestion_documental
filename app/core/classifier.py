from __future__ import annotations

import re
from typing import Any
from core.text_utils import normalize_text


def _search(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)

    # 1. CERTIFICADO DE CALIDAD
    if (
        "CERTIFICADO DE CALIDAD" in text_u
        or "CERT. DE CALIDAD" in text_u
        or "CERTIFICADO" in name_u
    ):
        return "certificado_calidad"

    # 2. GUIA DE REMISION
    if (
        "GUIA REMISION ELECTRONICA" in text_u
        or "GUIA DE REMISION ELECTRONICA" in text_u
        or "GUIA DE REMISION" in text_u
        or re.search(r"\bNRO\.?\s*T\d{3}[- ]\d+\b", text_u)
        or re.search(r"\bT\d{3}[- ]\d+\b", name_u)
        or re.search(r"\bGR\d{3}[- ]\d+\b", name_u)
    ):
        return "guia_remision"

    # 3. ORDEN DE COMPRA
    if (
        "ORDEN DE COMPRA" in text_u
        or "ORDEN DE COMRA" in text_u
        or re.search(r"\bOC[- ]?\d{4,}\b", text_u)
        or re.search(r"\bOC[- ]?\d{4,}\b", name_u)
    ):
        return "orden_compra"

    # 4. FACTURA
    if (
        "FACTURA ELECTRONICA" in text_u
        or "FACTURA" in text_u
        or re.search(r"\bF\d{3,4}-\d+\b", text_u)
        or re.search(r"\bF\d{3,4}-\d+\b", name_u)
        or re.search(r"\bFE\d{2,4}-\d+\b", text_u)
        or re.search(r"\bFE\d{2,4}-\d+\b", name_u)
        or re.search(r"\bNRO\.?\s*F[A-Z0-9]{2,4}-\d+\b", text_u)
    ):
        return "factura"

    return "otro"


def extract_basic_fields(text: str, file_name: str) -> dict[str, Any]:
    text_u = normalize_text(text)
    doc_type = detect_tipo_documental(text, file_name)

    ruc = None
    serie = None
    numero = None
    fecha_emision = None
    importe = None
    oc = None

    # RUC
    ruc = _search(r"\bRUC[:\s]*([0-9]{11})\b", text_u)
    if not ruc:
        ruc = _search(r"\bR\.U\.C\.?\s*(?:N[°º.]?)?\s*([0-9]{11})\b", text_u)
    if not ruc:
        ruc = _search(r"\bREG\.?\s*UNICO DE CONTRIBUYENTES[:\s]*([0-9]{11})\b", text_u)

    # Serie / número por tipo
    if doc_type == "factura":
        patrones = [
            r"\b(F\d{3,4})[- ](\d{3,})\b",
            r"\b(FE\d{2,4})[- ](\d{3,})\b",
            r"\bN[°º]\s*(F[A-Z0-9]{2,4})[- ](\d{3,})\b",
            r"\bNRO\.?\s*(F[A-Z0-9]{2,4})[- ](\d{3,})\b",
        ]
        for patron in patrones:
            m = re.search(patron, text_u, re.IGNORECASE)
            if m:
                serie = m.group(1).strip()
                numero = m.group(2).strip()
                break

    elif doc_type == "guia_remision":
        patrones = [
            r"\b(T\d{3})[- ](\d{3,})\b",
            r"\b(GR\d{3})[- ](\d{3,})\b",
            r"\bNRO\.?\s*(T\d{3})[- ](\d{3,})\b",
        ]
        for patron in patrones:
            m = re.search(patron, text_u, re.IGNORECASE)
            if m:
                serie = m.group(1).strip()
                numero = m.group(2).strip()
                break

    elif doc_type == "orden_compra":
        patrones = [
            r"\bOC[- ]?(\d{4,})\b",
            r"\bORDEN DE COMPRA\s*N[^0-9]{0,5}([0-9]{4,})\b",
        ]
        for patron in patrones:
            m = re.search(patron, text_u, re.IGNORECASE)
            if m:
                serie = "OC"
                numero = m.group(1).strip()
                break

    # Fecha de emisión
    fecha_emision = _search(
        r"\bFECHA(?: DE EMISION| DE EMISION:| DE EMISION\s*:)?\s*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})\b",
        text_u,
    )

    if not fecha_emision:
        fecha_emision = _search(r"\b([0-9]{2}/[0-9]{2}/[0-9]{4})\b", text_u)

    if not fecha_emision:
        fecha_emision = _search(r"\b([0-9]{2}-[0-9]{2}-[0-9]{4})\b", text_u)

    if not fecha_emision:
        fecha_emision = _search(r"\b([0-9]{2}-[A-Z]{3}-[0-9]{4})\b", text_u)

    if not fecha_emision:
        fecha_emision = _search(
            r"\b([0-9]{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DEL\s+[0-9]{4})\b",
            text_u,
        )

    # OC dentro de factura o guía
    oc = _search(r"\bOC[:\s]*([0-9]{4,})\b", text_u)
    if not oc:
        oc = _search(r"\bN[°º]?\s*OC[:\s]*([0-9]{4,})\b", text_u)

    # Importe
    # Se priorizan textos más cercanos al total final
    patrones_importe = [
        r"\bIMPORTE TOTAL[:\sA-Z$/.]*([0-9][0-9.,]*)\b",
        r"\bTOTAL\s*\(S/\)\s*[:.]?\s*([0-9][0-9.,]*)\b",
        r"\bTOTAL\s*\(USD \$\)\s*[:.]?\s*([0-9][0-9.,]*)\b",
        r"\bIMPORTE TOTAL\s*[:.]?\s*([0-9][0-9.,]*)\b",
        r"\bTOTAL[:\sA-Z$/.]*([0-9][0-9.,]*)\b",
    ]

    for patron in patrones_importe:
        m = re.search(patron, text_u, re.IGNORECASE)
        if m:
            importe = m.group(1).strip()
            break

    return {
        "tipo_documental": doc_type,
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "fecha_emision": fecha_emision,
        "importe": importe,
        "oc": oc,
    }