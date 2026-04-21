import re
from core.text_utils import normalize_text


def _search(pattern: str, text: str, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def detect_tipo_documental(text: str, file_name: str) -> str:
    text_u = normalize_text(text)
    name_u = normalize_text(file_name)

    if "FACTURA" in text_u or re.search(r"\bF[A-Z0-9]{2,4}-\d+\b", text_u):
        return "factura"

    if "ORDEN DE COMPRA" in text_u or name_u.startswith("OC"):
        return "orden_compra"

    if "GUIA DE REMISION" in text_u or "GUIA ELECTRONICA" in text_u:
        return "guia_remision"

    return "otro"


def extract_basic_fields(text: str, file_name: str) -> dict:
    text_u = normalize_text(text)

    tipo_documental = detect_tipo_documental(text, file_name)

    serie = None
    numero = None
    ruc = None
    fecha_emision = None
    importe = None
    oc = None

    # =========================
    # FACTURA (F231, FE65, etc)
    # =========================
    if tipo_documental == "factura":
        patrones = [
            r"\b(F\d{3,4})[- ](\d{3,})\b",              # F231-0101493
            r"\b(FE\d{2,4})[- ](\d{3,})\b",             # FE65-0812829
            r"\bN[°º]\s*(F[A-Z0-9]{2,4})[- ](\d{3,})\b",
            r"\bNRO\.?\s*(F[A-Z0-9]{2,4})[- ](\d{3,})\b",
        ]

        for p in patrones:
            m = re.search(p, text_u)
            if m:
                serie = m.group(1)
                numero = m.group(2)
                break

    # =========================
    # ORDEN DE COMPRA
    # =========================
    if tipo_documental == "orden_compra":
        m = re.search(r"\bOC[- ]?(\d{4,})\b", text_u)
        if m:
            serie = "OC"
            numero = m.group(1)

    # =========================
    # GUÍA DE REMISIÓN
    # =========================
    if tipo_documental == "guia_remision":
        m = re.search(r"\b(T\d{3})[- ](\d{3,})\b", text_u)
        if m:
            serie = m.group(1)
            numero = m.group(2)

    # =========================
    # RUC
    # =========================
    ruc = _search(r"\bRUC[:\s]*([0-9]{11})\b", text_u)

    # =========================
    # FECHA
    # =========================
    fecha_emision = _search(
        r"\bFECHA DE EMISION[:\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})\b",
        text_u,
    )

    if not fecha_emision:
        fecha_emision = _search(
            r"\b([0-9]{2}/[0-9]{2}/[0-9]{4})\b",
            text_u,
        )

    # Fecha larga tipo: 21 DE ABRIL DEL 2026
    if not fecha_emision:
        fecha_emision = _search(
            r"\b([0-9]{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DEL\s+[0-9]{4})\b",
            text_u,
        )

    # =========================
    # IMPORTE
    # =========================
    importe = _search(
        r"TOTAL.*?([0-9]+[.,][0-9]{2})",
        text_u,
        flags=re.DOTALL,
    )

    # =========================
    # ORDEN DE COMPRA (desde factura)
    # =========================
    oc = _search(r"\bOC[:\s]*([0-9]{4,})\b", text_u)

    return {
        "tipo_documental": tipo_documental,
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "fecha_emision": fecha_emision,
        "importe": importe,
        "oc": oc,
    }