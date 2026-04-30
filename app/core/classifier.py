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

    value = str(value).replace(",", "").strip()

    try:
        return float(value)
    except Exception:
        return None


def _compact_text(value: str | None) -> str:
    if not value:
        return ""

    value = normalize_text(value)
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _is_factura_text(text_u: str, name_u: str) -> bool:
    compact = _compact_text(text_u)

    return bool(
        "FACTURA ELECTRONICA" in text_u
        or "FACTURAELECTRONICA" in compact
        or re.search(rf"\b{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", text_u, re.IGNORECASE)
        or re.search(rf"\b{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b", name_u, re.IGNORECASE)
        or re.search(
            rf"\b\d{{11}}-\d{{2}}-{FACTURA_SERIE_RE}-{FACTURA_NUMERO_RE}\b",
            name_u,
            re.IGNORECASE,
        )
    )


def _is_guia_text(text_u: str, name_u: str) -> bool:
    compact = _compact_text(text_u)

    return bool(
        "GUIADEREMISIONELECTRONICA" in compact
        or "GUIAREMISIONELECTRONICA" in compact
        or re.search(r"GUIA\s+(DE\s+)?REMISION\s+ELECTRONICA", text_u, re.IGNORECASE | re.DOTALL)
        or re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", text_u, re.IGNORECASE)
        or re.search(rf"\b{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b", name_u, re.IGNORECASE)
        or re.search(
            rf"\b\d{{11}}-\d{{2}}-{GUIA_SERIE_RE}-{GUIA_NUMERO_RE}\b",
            name_u,
            re.IGNORECASE,
        )
    )


def _score_orden_compra(text_u: str, name_u: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    fuentes = f"{text_u}\n{name_u}"
    compact = _compact_text(fuentes)

    if re.search(
        r"ORDEN\s+DE\s+COM\w{0,4}.{0,120}?[0-9]{4,}",
        fuentes,
        re.IGNORECASE | re.DOTALL,
    ):
        score += 70
        reasons.append("orden_compra_con_numero")

    if re.search(
        r"ORDEN\s+COMPRA.{0,120}?[0-9]{4,}",
        fuentes,
        re.IGNORECASE | re.DOTALL,
    ):
        score += 60
        reasons.append("orden_compra_sin_de")

    if re.search(
        r"OC\s*BBTI.{0,80}?[0-9]{4,}",
        fuentes,
        re.IGNORECASE | re.DOTALL,
    ):
        score += 70
        reasons.append("ocbbti_con_numero")

    if re.search(r"\bOC[:\s-]*[0-9]{4,}", fuentes, re.IGNORECASE):
        score += 50
        reasons.append("oc_abreviado")

    if re.search(r"\b[0-9]{4,}\.PDF\b", name_u, re.IGNORECASE):
        score += 35
        reasons.append("nombre_solo_numero_pdf")

    if "ORDENDECOMPRA" in compact or "ORDENDECOMRA" in compact:
        score += 40
        reasons.append("compact_orden_compra")

    if "BBTISAC" in compact or "20565747356" in compact:
        score += 20
        reasons.append("senal_bbti")

    if "PRESENTACIONDECOMPROBANTESDEPAGO" in compact:
        score += 15
        reasons.append("bloque_presentacion_pago")

    return score, reasons


def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)

    for candidate in extract_qr_candidates(text):
        qr = parse_qr_payload(candidate)
        if qr and qr.get("tipo_documental") in ("factura", "guia_remision"):
            return qr["tipo_documental"]

    if _is_factura_text(text_u, name_u):
        return "factura"

    if _is_guia_text(text_u, name_u):
        return "guia_remision"

    score_oc, _ = _score_orden_compra(text_u, name_u)
    if score_oc >= 60:
        return "orden_compra"

    return "otro"


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
    fuentes = f"{text_u}\n{name_u}"

    patrones = [
        r"ORDEN\s+DE\s+COM\w{0,4}.{0,120}?([0-9]{4,})",
        r"ORDEN\s+COMPRA.{0,120}?([0-9]{4,})",
        r"OC\s*BBTI.{0,80}?([0-9]{4,})",
        r"\bOC[:\s-]*([0-9]{4,})\b",
        r"\b([0-9]{4,})\.PDF\b",
    ]

    for patron in patrones:
        m = re.search(patron, fuentes, re.IGNORECASE | re.DOTALL)
        if m:
            numero = m.group(1)
            if 4 <= len(numero) <= 8:
                return "OC", numero

    return None, None


def _extract_oc_ruc(text_u: str) -> str | None:
    rucs = re.findall(r"\b(20\d{9})\b", text_u)

    for ruc in rucs:
        if ruc != "20565747356":
            return ruc

    return None


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

    if doc_type == "factura":
        serie, numero = _extract_factura_fields(text_u, name_u)

    elif doc_type == "guia_remision":
        serie, numero = _extract_guia_fields(text_u, name_u)

    elif doc_type == "orden_compra":
        serie, numero = _extract_oc_fields(text_u, name_u)

    if doc_type == "factura":
        patrones_ruc_factura = [
            r"FACTURA ELECTRONICA.{0,400}?R\.?U\.?C\.?[:\s]*([0-9]{11})",
            r"R\.?U\.?C\.?[:\s]*([0-9]{11}).{0,400}?FACTURA ELECTRONICA",
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

    if not ruc and doc_type == "orden_compra":
        ruc = _extract_oc_ruc(text_u)

    if not ruc:
        for patron in [
            r"\bRUC[:\s]*([0-9]{11})\b",
            r"\bR\.?U\.?C\.?\s*:\s*[\r\n\s]*([0-9]{11})\b",
            r"\bR\.?U\.?C\.?[:\s]*([0-9]{11})\b",
            r"\bREG\.?\s*UNICO\s+DE\s+CONTRIBUYENTES[:\s]*([0-9]{11})\b",
        ]:
            m = re.search(patron, text_u, re.IGNORECASE | re.DOTALL)
            if m:
                ruc = m.group(1)
                break

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

    _, oc_detectada = _extract_oc_fields(text_u, name_u)
    if oc_detectada:
        oc = oc_detectada

    if doc_type == "orden_compra" and oc and not numero:
        serie = "OC"
        numero = oc

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