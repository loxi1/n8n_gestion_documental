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

    if tipo_documental and ruc and serie and numero:
        return sanitize_filename(f"{tipo_documental.upper()}_{ruc}_{serie}_{numero}{ext}")

    stem = sanitize_filename(Path(fallback_name).stem)
    return f"DOC_{stem}{ext}"


def move_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))