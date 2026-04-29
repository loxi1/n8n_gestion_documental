from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path


def sanitize_filename(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'[<>:"/\\|?*]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_token(value: str | None) -> str:
    if not value:
        return ""

    value = sanitize_filename(str(value))
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
    prefijo_nombre: str | None = None,
) -> str:
    ext = Path(fallback_name).suffix.lower() or ".pdf"

    tipo_map = {
        "factura": "FACTURA",
        "adjunto_factura": "ADJUNTO_FACTURA",
        "guia_remision": "GUIA_REMISION",
        "orden_compra": "ORDEN_COMPRA",
        "requerimiento_compra": "REQUERIMIENTO_COMPRA",
        "cotizacion": "COTIZACION",
        "certificado_calidad": "CERTIFICADO_CALIDAD",
        "nota_credito": "NOTA_CREDITO",
        "nota_debito": "NOTA_DEBITO",
        "otro": "OTRO",
    }

    tipo_txt = tipo_map.get(tipo_documental, "OTRO")
    serie_txt = normalize_token(serie)
    numero_txt = normalize_token(numero)
    ruc_txt = normalize_token(ruc_emisor)
    razon_txt = normalize_token(razon_social_emisor) or "SIN_RAZON_SOCIAL"

    inicio = normalize_token(prefijo_nombre) if prefijo_nombre else grupo_codigo
    parts: list[str] = [inicio, tipo_txt]

    if tipo_documental in (
        "factura",
        "guia_remision",
        "nota_credito",
        "nota_debito",
    ):
        if serie_txt:
            parts.append(serie_txt)
        if numero_txt:
            parts.append(numero_txt)

    elif tipo_documental in (
        "orden_compra",
        "requerimiento_compra",
        "cotizacion",
    ):
        if serie_txt:
            parts.append(serie_txt)
        if numero_txt:
            parts.append(numero_txt)

    elif tipo_documental == "adjunto_factura":
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