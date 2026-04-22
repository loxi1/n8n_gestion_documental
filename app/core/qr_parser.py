from __future__ import annotations

from typing import Any

from core.text_utils import normalize_text


TIPO_DOC_MAP = {
    "01": "factura",
    "03": "boleta",
    "07": "nota_credito",
    "08": "nota_debito",
}


def parse_qr_payload(qr_text: str | None) -> dict[str, Any] | None:
    """
    Formato SUNAT esperado, separado por "|":
    RUC|TIPO_DOC|SERIE|NUMERO|IGV|TOTAL|FECHA|TIPO_DOC_ADQ|NUM_DOC_ADQ|VALOR_RESUMEN|VALOR_FIRMA
    Puede venir con menos o más campos al final.
    """
    if not qr_text:
        return None

    raw = qr_text.strip()
    parts = [p.strip() for p in raw.split("|")]

    if len(parts) < 9:
        return None

    ruc_emisor = parts[0] or None
    tipo_doc = parts[1] or None
    serie = parts[2] or None
    numero = parts[3] or None
    igv = parts[4] or None
    total = parts[5] or None
    fecha = parts[6] or None
    tipo_doc_adquirente = parts[7] or None
    num_doc_adquirente = parts[8] or None
    valor_resumen = parts[9] if len(parts) > 9 and parts[9] else None
    valor_firma = parts[10] if len(parts) > 10 and parts[10] else None

    tipo_documental = TIPO_DOC_MAP.get(tipo_doc)

    if not ruc_emisor or not tipo_doc or not serie or not numero:
        return None

    return {
        "ruc_emisor": ruc_emisor,
        "tipo_doc_codigo": tipo_doc,
        "tipo_documental": tipo_documental,
        "serie": serie,
        "numero": numero,
        "igv": igv,
        "importe": total,
        "fecha_emision": fecha,
        "tipo_doc_adquirente": tipo_doc_adquirente,
        "num_doc_adquirente": num_doc_adquirente,
        "valor_resumen": valor_resumen,
        "valor_firma": valor_firma,
    }


def extract_qr_candidates(text: str | None) -> list[str]:
    """
    Busca líneas o bloques tipo QR SUNAT con separador '|'.
    """
    if not text:
        return []

    candidates: list[str] = []
    for line in str(text).splitlines():
        line = line.strip()
        if "|" in line and len(line.split("|")) >= 9:
            candidates.append(line)

    # fallback: buscar en texto colapsado
    text_u = normalize_text(text)
    if "|" in text_u and not candidates:
        chunks = text_u.split()
        joined = " ".join(chunks)
        if joined.count("|") >= 8:
            candidates.append(joined)

    return candidates