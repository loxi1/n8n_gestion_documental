from __future__ import annotations

import re
from typing import Any

from core.text_utils import normalize_text
from core.qr_parser import extract_qr_candidates, parse_qr_payload


FACTURA_SERIE_RE = r"F[A-Z0-9]{3}"
FACTURA_NUMERO_RE = r"\d{1,8}"

GUIA_SERIE_RE = r"(?:T[A-Z0-9]{3}|GR[A-Z0-9]{2,3})"
GUIA_NUMERO_RE = r"\d{1,8}"


def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)

    # 0. QR válido manda
    for candidate in extract_qr_candidates(text):
        qr = parse_qr_payload(candidate)
        if qr and qr.get("tipo_documental") == "factura":
            return "factura"

    # 1. Certificado
    if (
        "CERTIFICADO DE CALIDAD" in text_u
        or "CERT. DE CALIDAD" in text_u
        or "CERTIFICADO" in name_u
    ):
        return "certificado_calidad"

    # 2. Factura por nombre fuerte
    if (
        re.search(rf"\b{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", name_u)
        or re.search(rf"\b\d{{11}}-\d{{2}}-{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", name_u)
    ):
        return "factura"

    # 3. Guía por nombre fuerte
    if (
        re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", name_u)
        or re.search(rf"\b\d{{11}}-\d{{2}}-{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", name_u)
    ):
        return "guia_remision"

    # 4. Factura por texto fuerte
    if (
        "FACTURA ELECTRONICA" in text_u
        or re.search(rf"\b{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", text_u)
        or re.search(rf"\bNRO\s*{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", text_u)
    ):
        return "factura"

    # 5. Guía por texto fuerte
    if (
        "GUIA REMISION ELECTRONICA" in text_u
        or "GUIA DE REMISION ELECTRONICA" in text_u
        or re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", text_u)
        or re.search(rf"\bNRO\s*{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", text_u)
    ):
        return "guia_remision"

    # 6. Orden de compra real
    if (
        re.search(r"\bORDEN DE COMPRA\s*N(?:RO)?[°º:\s-]*\d{4,}\b", text_u)
        or re.search(r"\bORDEN DE COMRA\s*N(?:RO)?[°º:\s-]*\d{4,}\b", text_u)
        or re.search(r"\bORDEN DE COMPRA\b", name_u)
        or re.search(r"\bOC[- ]?\d{4,}\b", name_u)
    ):
        return "orden_compra"

    # 7. Requerimiento
    if (
        "REQUERIMIENTO DE COMPRA" in text_u
        or "REQUERIMIENTO" in text_u
        or re.search(r"\bREQ[- ]?\d{3,}\b", text_u)
        or re.search(r"\bREQ[- ]?\d{3,}\b", name_u)
    ):
        return "requerimiento_compra"

    # 8. Cotización
    if (
        "COTIZACION" in text_u
        or "PROFORMA" in text_u
        or "COTIZACION" in name_u
        or "PROFORMA" in name_u
    ):
        return "cotizacion"

    return "otro"


def _extract_factura_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    patrones = [
        rf"\b({FACTURA_SERIE_RE})-({FACTURA_NUMERO_RE})\b",
        rf"\bNRO\s*({FACTURA_SERIE_RE})-({FACTURA_NUMERO_RE})\b",
    ]
    for fuente in (text_u, name_u):
        for patron in patrones:
            m = re.search(patron, fuente, re.IGNORECASE)
            if m:
                return m.group(1), m.group(2)
    return None, None


def _extract_guia_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    patrones = [
        rf"\b({GUIA_SERIE_RE})-({GUIA_NUMERO_RE})\b",
        rf"\bNRO\s*({GUIA_SERIE_RE})-({GUIA_NUMERO_RE})\b",
    ]
    for fuente in (text_u, name_u):
        for patron in patrones:
            m = re.search(patron, fuente, re.IGNORECASE)
            if m:
                return m.group(1), m.group(2)
    return None, None


def extract_basic_fields(text: str, file_name: str) -> dict[str, Any]:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)
    doc_type = detect_tipo_documental(text, file_name)

    ruc = None
    serie = None
    numero = None
    fecha_emision = None
    importe = None
    oc = None
    qr_data = None

    # 1. QR primero
    for candidate in extract_qr_candidates(text):
        qr_data = parse_qr_payload(candidate)
        if qr_data:
            break

    if qr_data and qr_data.get("tipo_documental") == "factura":
        return {
            "tipo_documental": "factura",
            "serie": qr_data.get("serie"),
            "numero": qr_data.get("numero"),
            "ruc": qr_data.get("ruc_emisor"),
            "fecha_emision": qr_data.get("fecha_emision"),
            "importe": qr_data.get("importe"),
            "igv": qr_data.get("igv"),
            "oc": None,
            "qr_data": qr_data,
        }

    # 2. RUC
    for patron in [
        r"\bRUC[:\s]*([0-9]{11})\b",
        r"\bR\.?U\.?C\.?[:\s]*([0-9]{11})\b",
        r"\bREG\.?\s*UNICO DE CONTRIBUYENTES[:\s]*([0-9]{11})\b",
    ]:
        m = re.search(patron, text_u, re.IGNORECASE)
        if m:
            ruc = m.group(1)
            break

    # 3. Serie / número
    if doc_type == "factura":
        serie, numero = _extract_factura_fields(text_u, name_u)

    elif doc_type == "guia_remision":
        serie, numero = _extract_guia_fields(text_u, name_u)

    elif doc_type == "orden_compra":
        m = re.search(r"\bORDEN DE COM(?:P|R)A\s*N(?:RO)?[°º:\s-]*([0-9]{4,})\b", text_u, re.IGNORECASE)
        if not m:
            m = re.search(r"\bOC[- ]?([0-9]{4,})\b", text_u, re.IGNORECASE)
        if m:
            serie = "OC"
            numero = m.group(1)

    elif doc_type == "requerimiento_compra":
        m = re.search(r"\bREQ[- ]?(\d{3,})\b", text_u, re.IGNORECASE)
        if not m:
            m = re.search(r"\bREQUERIMIENTO(?: DE COMPRA)?\s*[:\-]?\s*([0-9]{3,})\b", text_u, re.IGNORECASE)
        if m:
            serie = "REQ"
            numero = m.group(1)

    # 4. Fecha de emisión
    # Prioridad:
    # 1) etiquetas explícitas
    # 2) búsqueda cercana a "F. EMISION"
    # 3) fallback contextual en factura

    # 4.1 Fecha explícita en misma línea
    for patron in [
        r"\bFECHA DE EMISION[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
        r"\bF\.?\s*EMISION[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
        r"\bFECHA DE EMISION[:\s]*([0-9]{2}-[0-9]{2}-[0-9]{4})\b",
        r"\bF\.?\s*EMISION[:\s]*([0-9]{2}-[0-9]{2}-[0-9]{4})\b",
        r"\bFECHA\s*[:\-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
    ]:
        m = re.search(patron, text_u, re.IGNORECASE)
        if m:
            fecha_emision = m.group(1)
            break

    # 4.2 Fecha cerca de "F. EMISION" aunque esté en otra línea o separada
    if not fecha_emision:
        m = re.search(
            r"F\.?\s*EMISION[:\s]*.{0,80}?([0-9]{2}/[0-9]{2}/[0-9]{4})",
            text_u,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            fecha_emision = m.group(1)

    # 4.3 Fallback especial para factura:
    # buscar una fecha cercana al bloque donde aparece FACTURA + serie/número
    if not fecha_emision and doc_type == "factura":
        m_fact = re.search(
            rf"FACTURA ELECTRONICA.*?({FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE})",
            text_u,
            re.IGNORECASE | re.DOTALL,
        )
        if m_fact:
            start = max(0, m_fact.start() - 250)
            end = min(len(text_u), m_fact.end() + 250)
            window = text_u[start:end]

            fechas = re.findall(r"\b([0-9]{2}/[0-9]{2}/[0-9]{4})\b", window)
            if fechas:
                # tomar la primera fecha del bloque, normalmente emisión
                fecha_emision = fechas[0]

    # 5. OC referencial
    for patron in [
        r"\bNRO\s*OC[:\s]*([0-9]{4,})\b",
        r"\bOC[:\s]*([0-9]{4,})\b",
        r"\bORDEN COMPRA[:\s]*([0-9]{4,})\b",
    ]:
        m = re.search(patron, text_u, re.IGNORECASE)
        if m:
            oc = m.group(1)
            break

    # 6. Importe
    for patron in [
        r"\bTOTAL\s*\(USD \$\)\s*[:.]?\s*([0-9][0-9,.\s]*)\b",
        r"\bTOTAL\s*\(S/\)\s*[:.]?\s*([0-9][0-9,.\s]*)\b",
        r"\bTOTAL A PAGAR[:\s]*([0-9][0-9,.\s]*)\b",
        r"\bIMPORTE TOTAL[:\sA-Z$/.]*([0-9][0-9,.\s]*)\b",
        r"\bTOTAL\s*S/\s*([0-9][0-9,.\s]*)\b",
    ]:
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
        "igv": None,
        "oc": oc,
        "qr_data": qr_data,
    }