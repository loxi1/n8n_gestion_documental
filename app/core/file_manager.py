from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path


def sanitize_filename(value: str) -> str:
    """
    Limpieza general para nombres de archivo:
    - quita tildes
    - elimina caracteres inválidos de Windows
    - compacta espacios
    """
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'[<>:"/\\|?*]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_token(value: str | None) -> str:
    """
    Normaliza un bloque interno del nombre:
    - limpia caracteres
    - cambia espacios por guion bajo
    """
    if not value:
        return ""

    value = sanitize_filename(value)
    value = value.replace(".", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace(" ", "_")
    return value


def build_final_name(
    grupo_codigo: str,
    tipo_documental: str,
    serie: str | None,
    numero: str | None,
    ruc_emisor: str | None,
    razon_social_emisor: str | None,
    fallback_name: str,
) -> str:
    ext = Path(fallback_name).suffix.lower() or ".pdf"

    tipo_map = {
        "factura": "FACTURA",
        "adjunto_factura": "ADJUNTO_FACTURA",
        "guia": "GUIA",
        "orden_compra": "ORDEN_COMPRA",
        "requerimiento_compra": "REQUERIMIENTO_COMPRA",
        "nota_credito": "NOTA_CREDITO",
        "otro": "OTRO",
    }

    tipo_txt = tipo_map.get(tipo_documental, "OTRO")
    serie_txt = normalize_token(serie)
    numero_txt = normalize_token(numero)
    ruc_txt = normalize_token(ruc_emisor)
    razon_txt = normalize_token(razon_social_emisor) or "SIN_RAZON_SOCIAL"

    parts: list[str] = [grupo_codigo, tipo_txt]

    if tipo_documental in ["factura", "guia"]:
        if serie_txt:
            parts.append(serie_txt)
        if numero_txt:
            parts.append(numero_txt)

    elif tipo_documental in ["orden_compra", "requerimiento_compra", "nota_credito"]:
        if numero_txt:
            parts.append(numero_txt)

    elif tipo_documental == "adjunto_factura":
        # no agrega serie/numero si no existen
        pass

    else:
        if serie_txt:
            parts.append(serie_txt)
        if numero_txt:
            parts.append(numero_txt)

    if ruc_txt:
        parts.append(ruc_txt)

    parts.append(razon_txt)

    return " ".join(parts) + ext


def move_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))