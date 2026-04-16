from __future__ import annotations

from pathlib import Path

from core.config import STORAGE_DIR
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
WHERE d.estado_documento = 'pendiente'
  AND a.estado_archivo = 'descargado'
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

    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as exc:
        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                """
                UPDATE documentos
                SET estado_documento = 'error', actualizado_en = NOW()
                WHERE id = %s
                """,
                (documento_id,),
            )
        print(f"[ERROR] No se pudo leer PDF {pdf_path}: {exc}")
        return

    if not text.strip():
        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                """
                UPDATE documentos
                SET estado_documento = 'no_identificado', actualizado_en = NOW()
                WHERE id = %s
                """,
                (documento_id,),
            )
        print(f"[WARN] PDF sin texto extraíble: {pdf_path}")
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

    destino_relativo = f"pendientes_clasificados/{pdf_path.parent.parent.name}/{pdf_path.parent.name}/{nuevo_nombre}"
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