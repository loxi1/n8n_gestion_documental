from __future__ import annotations

import re
from typing import Any

from core.text_utils import normalize_text
from core.qr_parser import extract_qr_candidates, parse_qr_payload


FACTURA_SERIE_RE = r"F[A-Z0-9]{3}"
FACTURA_NUMERO_RE = r"\d{1,8}"

GUIA_SERIE_RE = r"(?:T[A-Z0-9]{3}|GR[A-Z0-9]{2,3})"
GUIA_NUMERO_RE = r"\d{1,8}"


# =========================
# UTILIDAD IMPORTANTE
# =========================
def clean_number(value: str | None) -> float | None:
    if not value:
        return None
    value = value.replace(",", "").strip()
    try:
        return float(value)
    except:
        return None


# =========================
# DETECCION TIPO DOCUMENTO
# =========================
def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)

    # 0. QR manda
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

    # 3. Guía
    if (
        re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", name_u)
        or re.search(rf"\b\d{{11}}-\d{{2}}-{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", name_u)
    ):
        return "guia_remision"

    # 4. Factura por texto
    if (
        "FACTURA ELECTRONICA" in text_u
        or re.search(rf"\b{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", text_u)
    ):
        return "factura"

    # 5. Guía por texto
    if (
        "GUIA REMISION ELECTRONICA" in text_u
        or re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", text_u)
    ):
        return "guia_remision"

    # 6. Orden de compra REAL
    if (
        re.search(r"\bORDEN DE COMPRA\s*N(?:RO)?[°º:\s-]*\d{4,}\b", text_u)
        or re.search(r"\bOC[- ]?\d{4,}\b", text_u)
    ):
        return "orden_compra"

    return "otro"


# =========================
# EXTRACCION FACTURA
# =========================
def _extract_factura_fields(text_u: str, name_u: str):
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


# =========================
# EXTRACCION PRINCIPAL
# =========================
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

    # =========================
    # 1. QR (PRIORIDAD TOTAL)
    # =========================
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
            "importe": clean_number(qr_data.get("importe")),
            "igv": clean_number(qr_data.get("igv")),
            "oc": None,
            "qr_data": qr_data,
        }

    # =========================
    # 2. RUC DESDE NOMBRE (CLAVE)
    # =========================
    if doc_type == "factura":
        m = re.search(r"\b(\d{11})-\d{2}-F[A-Z0-9]{3}-\d+", name_u)
        if m:
            ruc = m.group(1)

    # fallback texto
    if not ruc:
        m = re.search(r"\bRUC[:\s]*([0-9]{11})\b", text_u)
        if m:
            ruc = m.group(1)

    # =========================
    # 3. SERIE / NUMERO
    # =========================
    if doc_type == "factura":
        serie, numero = _extract_factura_fields(text_u, name_u)

    # =========================
    # 4. FECHA (MEJORADA 🔥)
    # =========================
    # caso normal
    m = re.search(
        r"FECHA DE EMISION[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})",
        text_u,
        re.IGNORECASE,
    )
    if m:
        fecha_emision = m.group(1)

    # 🔥 NUEVO: salto de línea
    if not fecha_emision:
        m = re.search(
            r"F\.?\s*EMISION[:\s]*\n?\s*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})",
            text_u,
            re.IGNORECASE,
        )
        if m:
            fecha_emision = m.group(1)

    # fallback contextual
    if not fecha_emision and doc_type == "factura":
        fechas = re.findall(r"\b([0-9]{2}/[0-9]{2}/[0-9]{4})\b", text_u)
        if fechas:
            fecha_emision = fechas[0]

    # =========================
    # 5. IMPORTE
    # =========================
    m = re.search(r"TOTAL.*?([0-9][0-9,\.]+)", text_u, re.IGNORECASE)
    if m:
        importe = clean_number(m.group(1))

    # =========================
    # 6. OC
    # =========================
    m = re.search(r"\bOC[:\s]*([0-9]{4,})\b", text_u)
    if m:
        oc = m.group(1)

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