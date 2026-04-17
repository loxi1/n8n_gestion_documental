from __future__ import annotations

import re
import shutil
from pathlib import Path


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip()


def build_temp_classified_name(
    tipo_documental: str,
    ruc: str | None,
    serie: str | None,
    numero: str | None,
    fallback_name: str,
) -> str:
    ext = Path(fallback_name).suffix.lower() or ".pdf"

    if tipo_documental == "factura" and ruc and serie and numero:
        return sanitize_filename(f"FACTURA_{ruc}_{serie}_{numero}{ext}")

    if tipo_documental == "guia" and serie and numero:
        return sanitize_filename(f"GUIA_{serie}_{numero}{ext}")

    if tipo_documental == "orden_compra" and numero:
        return sanitize_filename(f"OC_{numero}{ext}")

    stem = sanitize_filename(Path(fallback_name).stem)
    return f"DOC_{stem}{ext}"


def move_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))

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
    razon_txt = sanitize_filename((razon_social_emisor or "").strip()) or "SIN_RAZON"

    tipo_map = {
        "factura": "FACTURA",
        "guia": "GUIA",
        "orden_compra": "OC",
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