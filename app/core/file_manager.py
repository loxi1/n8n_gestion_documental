from pathlib import Path
import re


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip()


def build_final_name(
    grupo_codigo: str,
    serie: str | None,
    numero: str | None,
    ruc_emisor: str | None,
    razon_social_emisor: str | None,
    tipo_documental: str,
    fallback_name: str,
) -> str:
    ext = Path(fallback_name).suffix.lower() or ".pdf"

    serie_txt = (serie or "").strip()
    numero_txt = (numero or "").strip()
    ruc_txt = (ruc_emisor or "").strip()
    razon_txt = sanitize_filename((razon_social_emisor or "").strip()) or "SIN_RAZON_SOCIAL"

    tipo_map = {
        "factura": "FACTURA",
        "guia": "GUIA",
        "orden_compra": "ORDEN_COMPRA",
        "nota": "NOTA",
        "otro": "OTRO",
    }
    tipo_txt = tipo_map.get(tipo_documental, "OTRO")

    parts = [grupo_codigo]

    if serie_txt:
        parts.append(serie_txt)
    if numero_txt:
        parts.append(numero_txt)
    if ruc_txt:
        parts.append(ruc_txt)

    parts.append(razon_txt)
    parts.append(tipo_txt)

    return sanitize_filename(" ".join(parts)) + ext