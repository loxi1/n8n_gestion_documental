from __future__ import annotations

from typing import Any


TIPO_DOC_MAP = {
    "01": "factura",
    "03": "boleta",
    "07": "nota_credito",
    "08": "nota_debito",
    "09": "guia_remision",
}


def parse_qr_payload(qr_text: str | None) -> dict[str, Any] | None:
    if not qr_text:
        return None

    raw = qr_text.strip().replace("\n", "").replace("\r", "")
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) < 8:
        return None

    ruc_emisor = parts[0] or None
    tipo_doc = parts[1] or None
    serie = parts[2] or None
    numero = parts[3] or None

    tipo_documental = TIPO_DOC_MAP.get(tipo_doc)

    if not ruc_emisor or not tipo_doc or not serie or not numero:
        return None

    # FACTURA / BOLETA / NC / ND
    if tipo_doc in ("01", "03", "07", "08"):
        if len(parts) < 9:
            return None

        return {
            "ruc_emisor": ruc_emisor,
            "tipo_doc_codigo": tipo_doc,
            "tipo_documental": tipo_documental,
            "serie": serie,
            "numero": numero,
            "igv": parts[4] or None,
            "importe": parts[5] or None,
            "fecha_emision": parts[6] or None,
            "tipo_doc_adquirente": parts[7] or None,
            "num_doc_adquirente": parts[8] or None,
            "valor_resumen": parts[9] if len(parts) > 9 and parts[9] else None,
            "valor_firma": parts[10] if len(parts) > 10 and parts[10] else None,
            "qr_raw": raw,
        }

    # GUÍA DE REMISIÓN ELECTRÓNICA
    if tipo_doc == "09":
        return {
            "ruc_emisor": ruc_emisor,
            "tipo_doc_codigo": tipo_doc,
            "tipo_documental": "guia_remision",
            "serie": serie,
            "numero": numero,
            "igv": None,
            "importe": None,
            "fecha_emision": parts[5] if len(parts) > 5 else None,
            "tipo_doc_adquirente": parts[6] if len(parts) > 6 else None,
            "num_doc_adquirente": parts[7] if len(parts) > 7 else None,
            "url_descarga": parts[8] if len(parts) > 8 else None,
            "qr_raw": raw,
        }

    return None


def extract_qr_candidates(text: str | None) -> list[str]:
    if not text:
        return []

    candidates: list[str] = []
    for line in str(text).splitlines():
        line = line.strip()
        if "|" in line and len(line.split("|")) >= 9:
            candidates.append(line)

    return candidates