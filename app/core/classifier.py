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

    # 1. Certificado
    if (
        "CERTIFICADO DE CALIDAD" in text_u
        or "CERT. DE CALIDAD" in text_u
        or "CERTIFICADO" in name_u
    ):
        return "certificado_calidad"

    # 2. Factura por nombre fuerte
    if (
        re.search(r"\bF[A-Z0-9]{3}-\d{1,8}\b", name_u)
        or re.search(r"\b\d{11}-\d{2}-F[A-Z0-9]{3}-\d{1,8}\b", name_u)
    ):
        return "factura"

    # 3. Guía por nombre fuerte
    if (
        re.search(r"\bT[A-Z0-9]{3}-\d{1,8}\b", name_u)
        or re.search(r"\bGR[A-Z0-9]{2,3}-\d{1,8}\b", name_u)
        or re.search(r"\b\d{11}-\d{2}-T[A-Z0-9]{3}-\d{1,8}\b", name_u)
    ):
        return "guia_remision"

    # 4. Guía por título real
    if (
        "GUIA REMISION ELECTRONICA" in text_u
        or "GUIA DE REMISION ELECTRONICA" in text_u
        or "GUIA DE REMISION" in text_u
        or re.search(r"\bNRO\s*T[A-Z0-9]{3}-\d{1,8}\b", text_u)
    ):
        return "guia_remision"

    # 5. Orden de compra
    if (
        "ORDEN DE COMPRA" in text_u
        or "ORDEN DE COMRA" in text_u
        or re.search(r"\bOC[- ]?\d{4,}\b", text_u)
        or re.search(r"\bOC[- ]?\d{4,}\b", name_u)
    ):
        return "orden_compra"

    # 6. Requerimiento
    if (
        "REQUERIMIENTO DE COMPRA" in text_u
        or "REQUERIMIENTO" in text_u
        or re.search(r"\bREQ[- ]?\d{3,}\b", text_u)
        or re.search(r"\bREQ[- ]?\d{3,}\b", name_u)
    ):
        return "requerimiento_compra"

    # 7. Cotización
    if (
        "COTIZACION" in text_u
        or "PROFORMA" in text_u
        or "COTIZACION" in name_u
        or "PROFORMA" in name_u
    ):
        return "cotizacion"

    # 8. Factura por texto
    if (
        "FACTURA ELECTRONICA" in text_u
        or "FACTURA" in text_u
        or re.search(r"\bNRO\s*F[A-Z0-9]{3}-\d{1,8}\b", text_u)
        or re.search(r"\bF[A-Z0-9]{3}-\d{1,8}\b", text_u)
    ):
        return "factura"

    return "otro"


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

    # RUC
    for patron in [
        r"\bRUC[:\s]*([0-9]{11})\b",
        r"\bR U C[:\s]*([0-9]{11})\b",
        r"\bREG UNICO DE CONTRIBUYENTES[:\s]*([0-9]{11})\b",
    ]:
        m = re.search(patron, text_u)
        if m:
            ruc = m.group(1)
            break

    # Serie / número
    if doc_type == "factura":
        patrones = [
            r"\b(F[A-Z0-9]{3})-(\d{1,8})\b",   # F231-0101575 / FE65-0812829 / FF12-7700
            r"\bNRO\s*(F[A-Z0-9]{3})-(\d{1,8})\b",
        ]
        for fuente in (text_u, name_u):
            for patron in patrones:
                m = re.search(patron, fuente)
                if m:
                    serie = m.group(1)
                    numero = m.group(2)
                    break
            if serie and numero:
                break

    elif doc_type == "guia_remision":
        patrones = [
            r"\b(T[A-Z0-9]{3})-(\d{1,8})\b",
            r"\b(GR[A-Z0-9]{2,3})-(\d{1,8})\b",
            r"\bNRO\s*(T[A-Z0-9]{3})-(\d{1,8})\b",
        ]
        for fuente in (text_u, name_u):
            for patron in patrones:
                m = re.search(patron, fuente)
                if m:
                    serie = m.group(1)
                    numero = m.group(2)
                    break
            if serie and numero:
                break

    elif doc_type == "orden_compra":
        for patron in [
            r"\bOC[- ]?(\d{4,})\b",
            r"\bORDEN DE COMPRA\s*NRO?\s*[:\-]?\s*([0-9]{4,})\b",
            r"\bORDEN DE COMPRA\s*([0-9]{4,})\b",
        ]:
            m = re.search(patron, text_u)
            if m:
                serie = "OC"
                numero = m.group(1)
                break

    elif doc_type == "requerimiento_compra":
        for patron in [
            r"\bREQ[- ]?(\d{3,})\b",
            r"\bREQUERIMIENTO(?: DE COMPRA)?\s*NRO?\s*[:\-]?\s*([0-9]{3,})\b",
        ]:
            m = re.search(patron, text_u)
            if m:
                serie = "REQ"
                numero = m.group(1)
                break

    # Fecha de emisión: priorizar emisión, no vencimiento
    for patron in [
        r"\bFECHA DE EMISION[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
        r"\bF EMISION[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
        r"\bF\. EMISION[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
        r"\bFECHA DE EMISION[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})\b",
        r"\bCALLAO,\s*([0-9]{1,2}\s+DE\s+[A-Z]+\s+DEL\s+[0-9]{4})\b",
        r"\b([0-9]{1,2}\s+DE\s+[A-Z]+\s+DEL\s+[0-9]{4})\b",
    ]:
        m = re.search(patron, text_u)
        if m:
            fecha_emision = m.group(1)
            break

    # OC relacionada
    for patron in [
        r"\bNRO\s*OC[:\s]*([0-9]{4,})\b",
        r"\bOC[:\s]*([0-9]{4,})\b",
    ]:
        m = re.search(patron, text_u)
        if m:
            oc = m.group(1)
            break

    # Importe total
    for patron in [
        r"\bIMPORTE TOTAL[:\sA-Z$/.]*([0-9][0-9.,]*)\b",
        r"\bTOTAL\s*\(USD \$\)\s*[:.]?\s*([0-9][0-9.,]*)\b",
        r"\bTOTAL\s*\(S/\)\s*[:.]?\s*([0-9][0-9.,]*)\b",
        r"\bIMPORTE TOTAL\s*[:.]?\s*([0-9][0-9.,]*)\b",
    ]:
        m = re.search(patron, text_u)
        if m:
            importe = m.group(1)
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