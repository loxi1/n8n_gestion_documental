from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from core.config import (
    STORAGE_DIR,
    OCR_TMP_DIR,
)
from core.db import get_cursor
from core.extractor_pdf import extract_text_from_pdf
from core.classifier import extract_basic_fields
from core.file_manager import build_temp_classified_name, move_file


SQL_SELECT_PENDING = """
SELECT
    d.id AS documento_id,
    a.id AS archivo_id,
    a.ruta_temporal,
    a.nombre_archivo_actual,
    a.nombre_archivo_original
FROM documentos d
JOIN archivos a ON a.documento_id = d.id
WHERE d.estado_documento IN ('pendiente', 'no_identificado')
  AND a.estado_archivo IN ('descargado', 'renombrado')
ORDER BY d.id ASC;
"""

SQL_UPDATE_DOCUMENTO = """
UPDATE documentos
SET
    tipo_documental = %(tipo_documental)s,
    ruc = %(ruc)s,
    serie = %(serie)s,
    numero = %(numero)s,
    fecha_emision = %(fecha_emision)s,
    importe = %(importe)s,
    estado_documento = %(estado_documento)s,
    actualizado_en = NOW()
WHERE id = %(documento_id)s;
"""

SQL_UPDATE_ARCHIVO = """
UPDATE archivos
SET
    nombre_archivo_actual = %(nombre_archivo_actual)s,
    ruta_temporal = %(ruta_temporal)s,
    estado_archivo = %(estado_archivo)s,
    actualizado_en = NOW()
WHERE id = %(archivo_id)s;
"""


def resolve_absolute_path(relative_path: str) -> Path:
    return STORAGE_DIR / relative_path


def to_wsl_path(path: Path) -> str:
    """
    Convierte:
    C:\\D\\Proyectos\\...  -> /mnt/c/D/Proyectos/...
    """
    raw = str(path.resolve()).replace("\\", "/")
    if len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].lower()
        rest = raw[2:]
        return f"/mnt/{drive}{rest}"
    return raw


def run_ocr(input_pdf: Path, output_pdf: Path) -> bool:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    system_name = platform.system().lower()

    # En Windows usaremos WSL
    if "windows" in system_name:
        input_wsl = to_wsl_path(input_pdf)
        output_wsl = to_wsl_path(output_pdf)

        cmd = [
            "wsl",
            "bash",
            "-lc",
            f'export PATH="$HOME/venvs/ocrpdf/bin:$PATH" && '
            f'ocrmypdf -l spa --force-ocr "{input_wsl}" "{output_wsl}"'
        ]
    else:
        # En Ubuntu producción
        cmd = [
            "ocrmypdf",
            "-l", "spa",
            "--force-ocr",
            str(input_pdf),
            str(output_pdf),
        ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            print("[OCR ERROR STDOUT]")
            print(result.stdout)
            print("[OCR ERROR STDERR]")
            print(result.stderr)
            return False

        return True

    except Exception as exc:
        print(f"[OCR EXCEPTION] {exc}")
        return False


def move_to_bucket(pdf_path: Path, bucket: str, fallback_name: str) -> tuple[str, str]:
    year = pdf_path.parent.parent.name
    month = pdf_path.parent.name
    destino_relativo = f"{bucket}/{year}/{month}/{fallback_name}"
    destino_abs = STORAGE_DIR / destino_relativo
    move_file(pdf_path, destino_abs)
    return fallback_name, destino_relativo


def process_one_document(item: dict) -> None:
    documento_id = item["documento_id"]
    archivo_id = item["archivo_id"]
    ruta_temporal = item["ruta_temporal"]
    nombre_archivo_actual = item["nombre_archivo_actual"]
    nombre_archivo_original = item["nombre_archivo_original"]

    pdf_path = resolve_absolute_path(ruta_temporal)

    if not pdf_path.exists():
        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                """
                UPDATE documentos
                SET estado_documento = 'error', actualizado_en = NOW()
                WHERE id = %s
                """,
                (documento_id,),
            )
            cur.execute(
                """
                UPDATE archivos
                SET estado_archivo = 'error', actualizado_en = NOW()
                WHERE id = %s
                """,
                (archivo_id,),
            )
        print(f"[ERROR] No existe archivo: {pdf_path}")
        return

    text = ""
    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as exc:
        print(f"[WARN] Error leyendo PDF directo {pdf_path.name}: {exc}")

    # Si no hay texto, intentar OCR
    if not text.strip():
        year = pdf_path.parent.parent.name
        month = pdf_path.parent.name
        ocr_output = OCR_TMP_DIR / year / month / f"ocr_{pdf_path.name}"

        ocr_ok = run_ocr(pdf_path, ocr_output)

        if ocr_ok and ocr_output.exists():
            try:
                text = extract_text_from_pdf(ocr_output)
                if text.strip():
                    print(f"[OCR OK] documento_id={documento_id} archivo={pdf_path.name}")
                else:
                    print(f"[OCR WARN] OCR generado pero sin texto útil: {pdf_path.name}")
            except Exception as exc:
                print(f"[OCR READ ERROR] {exc}")

    # Si sigue sin texto, mover a no_identificados
    if not text.strip():
        nuevo_nombre, destino_relativo = move_to_bucket(
            pdf_path,
            "no_identificados",
            nombre_archivo_actual,
        )

        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                SQL_UPDATE_DOCUMENTO,
                {
                    "tipo_documental": None,
                    "ruc": None,
                    "serie": None,
                    "numero": None,
                    "fecha_emision": None,
                    "importe": None,
                    "estado_documento": "no_identificado",
                    "documento_id": documento_id,
                },
            )
            cur.execute(
                SQL_UPDATE_ARCHIVO,
                {
                    "nombre_archivo_actual": nuevo_nombre,
                    "ruta_temporal": destino_relativo,
                    "estado_archivo": "renombrado",
                    "archivo_id": archivo_id,
                },
            )

        print(f"[WARN] No identificado: documento_id={documento_id} archivo={pdf_path.name}")
        return

    fields = extract_basic_fields(text, nombre_archivo_original)

    tipo_documental = fields["tipo_documental"]
    estado_documento = "clasificado" if tipo_documental != "otro" else "no_identificado"

    nuevo_nombre = build_temp_classified_name(
        tipo_documental=tipo_documental,
        ruc=fields["ruc"],
        serie=fields["serie"],
        numero=fields["numero"],
        fallback_name=nombre_archivo_actual,
    )

    year = pdf_path.parent.parent.name
    month = pdf_path.parent.name

    bucket = "pendientes_clasificados" if estado_documento == "clasificado" else "no_identificados"
    destino_relativo = f"{bucket}/{year}/{month}/{nuevo_nombre}"
    destino_abs = STORAGE_DIR / destino_relativo

    move_file(pdf_path, destino_abs)

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            SQL_UPDATE_DOCUMENTO,
            {
                "tipo_documental": tipo_documental,
                "ruc": fields["ruc"],
                "serie": fields["serie"],
                "numero": fields["numero"],
                "fecha_emision": fields["fecha_emision"],
                "importe": fields["importe"],
                "estado_documento": estado_documento,
                "documento_id": documento_id,
            },
        )
        cur.execute(
            SQL_UPDATE_ARCHIVO,
            {
                "nombre_archivo_actual": nuevo_nombre,
                "ruta_temporal": destino_relativo,
                "estado_archivo": "renombrado",
                "archivo_id": archivo_id,
            },
        )

    print(
        f"[OK] documento_id={documento_id} tipo={tipo_documental} "
        f"archivo={nuevo_nombre}"
    )


def main() -> None:
    with get_cursor() as (_, cur):
        cur.execute(SQL_SELECT_PENDING)
        rows = cur.fetchall()

    if not rows:
        print("No hay documentos pendientes.")
        return

    print(f"Pendientes encontrados: {len(rows)}")

    for row in rows:
        process_one_document(row)


if __name__ == "__main__":
    main()