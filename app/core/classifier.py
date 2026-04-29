from __future__ import annotations

import re
from typing import Any

from core.text_utils import normalize_text
from core.qr_parser import extract_qr_candidates, parse_qr_payload


FACTURA_SERIE_RE = r"F[A-Z0-9]{3}"
FACTURA_NUMERO_RE = r"\d{1,8}"

GUIA_SERIE_RE = r"(?:T[A-Z0-9]{3}|GR[A-Z0-9]{2,3})"
GUIA_NUMERO_RE = r"\d{1,8}"


def clean_number(value: str | None) -> float | None:
    if not value:
        return None
    value = value.replace(",", "").strip()
    try:
        return float(value)
    except Exception:
        return None


def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)
    text_email_u = normalize_email_like(text_u)

    # 0. QR manda para factura/guía
    for candidate in extract_qr_candidates(text):
        qr = parse_qr_payload(candidate)
        if qr and qr.get("tipo_documental"):
            return qr.get("tipo_documental")

    # 1. Orden de compra BBTI / consorcios
    patron_oc = r"\b(ORDEN\s+DE\s+COM\w{0,3}|ORDEN\s+COMPRA|OC)\b.{0,120}?[0-9]{4,}"

    if (
        re.search(patron_oc, text_u, re.IGNORECASE | re.DOTALL)
        or re.search(patron_oc, name_u, re.IGNORECASE | re.DOTALL)
        or re.search(r"\bOCBBTI\b", name_u, re.IGNORECASE)
        or re.search(r"\b\d{4,}\.PDF$", name_u, re.IGNORECASE)
    ):
        return "orden_compra"

    # 2. Factura por nombre
    if (
        re.search(rf"\b{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", name_u)
        or re.search(rf"\b\d{{11}}-\d{{2}}-{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", name_u)
    ):
        return "factura"

    # 3. Guía por nombre
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
        re.search(r"GUIA\s+(DE\s+)?REMISION\s+ELECTRONICA", text_u, re.IGNORECASE)
        or re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", text_u)
    ):
        return "guia_remision"

    return "otro"

def normalize_email_like(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()

def _extract_factura_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    patrones = [
        rf"\b({FACTURA_SERIE_RE})-({FACTURA_NUMERO_RE})\b",
        rf"\bNRO\s*({FACTURA_SERIE_RE})-({FACTURA_NUMERO_RE})\b",
        rf"\bN[°º]\s*({FACTURA_SERIE_RE})-({FACTURA_NUMERO_RE})\b",
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
        rf"\bNRO\.?\s*({GUIA_SERIE_RE})-({GUIA_NUMERO_RE})\b",
        rf"\bN[°º]\s*({GUIA_SERIE_RE})-({GUIA_NUMERO_RE})\b",
    ]

    for fuente in (text_u, name_u):
        for patron in patrones:
            m = re.search(patron, fuente, re.IGNORECASE)
            if m:
                return m.group(1), m.group(2)

    return None, None


def _extract_oc_fields(text_u: str, name_u: str) -> tuple[str | None, str | None]:
    patrones = [
        r"ORDEN\s+DE\s+COM\w{0,3}.*?([0-9]{4,})",
        r"ORDEN\s+COMPRA.*?([0-9]{4,})",
        r"OCBBTI.*?([0-9]{4,})",
        r"\bOC[:\s-]*([0-9]{4,})\b",
        r"\b([0-9]{4,})\.PDF\b",
    ]

    for fuente in (text_u, name_u):
        for patron in patrones:
            m = re.search(patron, fuente, re.IGNORECASE | re.DOTALL)
            if m:
                return "OC", m.group(1)

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

    # 1. QR prioridad total
    for candidate in extract_qr_candidates(text):
        qr_data = parse_qr_payload(candidate)
        if qr_data:
            break

    if qr_data and qr_data.get("tipo_documental") in ("factura", "guia_remision"):
        return {
            "tipo_documental": qr_data.get("tipo_documental"),
            "serie": qr_data.get("serie"),
            "numero": qr_data.get("numero"),
            "ruc": qr_data.get("ruc_emisor"),
            "fecha_emision": qr_data.get("fecha_emision"),
            "importe": qr_data.get("importe"),
            "igv": qr_data.get("igv"),
            "oc": None,
            "qr_data": qr_data,
        }

    # 2. Serie / número principal
    if doc_type == "factura":
        serie, numero = _extract_factura_fields(text_u, name_u)

    elif doc_type == "guia_remision":
        serie, numero = _extract_guia_fields(text_u, name_u)

    elif doc_type == "orden_compra":
        serie, numero = _extract_oc_fields(text_u, name_u)
    
    if doc_type == "orden_compra":
        print("====== DEBUG OC ======")
        print("TEXT:", text_u[:500])
        print("NAME:", name_u)
        print("SERIE:", serie)
        print("NUMERO:", numero)

    # 3. RUC emisor / proveedor
    if doc_type == "factura":
        patrones_ruc_factura = [
            r"FACTURA ELECTRONICA.{0,300}?R\.?U\.?C\.?[:\s]*([0-9]{11})",
            r"R\.?U\.?C\.?[:\s]*([0-9]{11}).{0,300}?FACTURA ELECTRONICA",
        ]
        for patron in patrones_ruc_factura:
            m = re.search(patron, text_u, re.IGNORECASE | re.DOTALL)
            if m:
                ruc = m.group(1)
                break

    if not ruc and doc_type == "factura":
        m = re.search(
            rf"\b(\d{{11}})-\d{{2}}-{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b",
            name_u,
            re.IGNORECASE,
        )
        if m:
            ruc = m.group(1)

    if not ruc and doc_type == "guia_remision":
        m = re.search(
            rf"\b(\d{{11}})-\d{{2}}-{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b",
            name_u,
            re.IGNORECASE,
        )
        if m:
            ruc = m.group(1)

    if not ruc:
        for patron in [
            r"\bRUC[:\s]*([0-9]{11})\b",
            r"\bR\.?U\.?C\.?[:\s]*([0-9]{11})\b",
            r"\bREG\.?\s*UNICO\s+DE\s+CONTRIBUYENTES[:\s]*([0-9]{11})\b",
        ]:
            m = re.search(patron, text_u, re.IGNORECASE)
            if m:
                ruc = m.group(1)
                break

    # 4. Fecha robusta
    patrones_fecha = [
        r"FECHA\s+DE\s+EMISION\s*[:\-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"FECHA\s+DE\s+EMISION\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"FECHA\s+DE\s+EMISION\s*[:\-]?\s*([0-9]{1,2}-[A-Z]{3}-[0-9]{4})",
        r"F\.?\s*EMISION\s*[:\-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})",
        r"F\.?\s*EMISION\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"F\.?\s*EMISION\s*[:\-]?\s*([0-9]{1,2}-[A-Z]{3}-[0-9]{4})",
        r"(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DEL\s+\d{4})",
    ]

    for patron in patrones_fecha:
        m = re.search(patron, text_u, re.IGNORECASE | re.DOTALL)
        if m:
            fecha_emision = m.group(1)
            break

    # 5. OC referencial dentro de factura/guía o como dato principal de OC
    _, oc_detectada = _extract_oc_fields(text_u, name_u)
    if oc_detectada:
        oc = oc_detectada

    if doc_type == "orden_compra" and oc and not numero:
        serie = "OC"
        numero = oc

    # 6. Importe
    for patron in [
        r"\bTOTAL\s*\(USD\s*\$?\)\s*[:.]?\s*([0-9][0-9,.\s]*)\b",
        r"\bTOTAL\s*\(S/\)\s*[:.]?\s*([0-9][0-9,.\s]*)\b",
        r"\bTOTAL\s+A\s+PAGAR[:\s]*([0-9][0-9,.\s]*)\b",
        r"\bIMPORTE\s+TOTAL[:\sA-Z$/.]*([0-9][0-9,.\s]*)\b",
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