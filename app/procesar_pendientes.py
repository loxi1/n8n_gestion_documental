from __future__ import annotations

from pathlib import Path

from core.config import (
    STORAGE_DIR,
    OCR_TMP_DIR,
    PENDIENTES_CLASIFICADOS_DIR,
    NO_IDENTIFICADOS_DIR,
)
from core.db import get_cursor
from core.extractor_pdf import extract_text_from_pdf
from core.classifier import extract_basic_fields
from core.file_manager import build_temp_classified_name, move_file
from core.ocr_service import run_ocr


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


def move_to_no_identificados(pdf_path: Path, fallback_name: str) -> tuple[str, str]:
    year = pdf_path.parent.parent.name
    month = pdf_path.parent.name
    destino_relativo = f"no_identificados/{year}/{month}/{fallback_name}"
    destino_abs = STORAGE_DIR / destino_relativo
    move_file(pdf_path, destino_abs)
    return fallback_name, destino_relativo


def procesar_documento(item: dict) -> None:
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
        print(f"[WARN] Error lectura directa PDF {pdf_path}: {exc}")

    # Si no hay texto, intentar OCR
    if not text.strip():
        ocr_output = OCR_TMP_DIR / pdf_path.parent.parent.name / pdf_path.parent.name / pdf_path.name
        ocr_ok = run_ocr(pdf_path, ocr_output)

        if ocr_ok and ocr_output.exists():
            try:
                text = extract_text_from_pdf(ocr_output)
                if text.strip():
                    # reemplazamos el original por el OCRado
                    move_file(ocr_output, pdf_path)
                    print(f"[OCR OK] documento_id={documento_id} archivo={pdf_path.name}")
                else:
                    print(f"[OCR WARN] OCR generado pero sin texto útil: {pdf_path.name}")
            except Exception as exc:
                print(f"[OCR ERROR] No se pudo leer OCR: {exc}")

    if not text.strip():
        nuevo_nombre, destino_relativo = move_to_no_identificados(pdf_path, nombre_archivo_actual)

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

        print(f"[WARN] No identificado: {pdf_path.name}")
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

    if estado_documento == "clasificado":
        destino_relativo = f"pendientes_clasificados/{year}/{month}/{nuevo_nombre}"
    else:
        destino_relativo = f"no_identificados/{year}/{month}/{nuevo_nombre}"

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
        f"[OK] documento_id={documento_id} tipo={tipo_documental} archivo={nuevo_nombre}"
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
        procesar_documento(row)


if __name__ == "__main__":
    main()