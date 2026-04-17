from __future__ import annotations

from datetime import date
from core.db import get_cursor


def get_next_correlativo_mes(fecha_emision: date, prefijo: str = "04") -> tuple[int, str]:
    year = fecha_emision.year
    month = fecha_emision.month

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            SELECT COALESCE(MAX(correlativo_mes), 0) AS max_corr
            FROM documentos
            WHERE fecha_emision IS NOT NULL
              AND EXTRACT(YEAR FROM fecha_emision) = %s
              AND EXTRACT(MONTH FROM fecha_emision) = %s
              AND grupo_codigo LIKE %s
            """,
            (year, month, f"{prefijo}-%"),
        )
        row = cur.fetchone()

    siguiente = int(row["max_corr"] or 0) + 1
    grupo_codigo = f"{prefijo}-{siguiente:04d}"
    return siguiente, grupo_codigo


def get_documentos_por_correo(correo_id: int) -> list[dict]:
    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT
                d.id AS documento_id,
                d.correo_id,
                d.tipo_documental,
                d.serie,
                d.numero,
                d.ruc,
                d.razon_social,
                d.fecha_emision,
                d.importe,
                d.estado_documento,
                a.id AS archivo_id,
                a.nombre_archivo_actual,
                a.nombre_archivo_original,
                a.ruta_temporal,
                a.estado_archivo
            FROM documentos d
            JOIN archivos a ON a.documento_id = d.id
            WHERE d.correo_id = %s
            ORDER BY d.id ASC
            """,
            (correo_id,),
        )
        return [dict(r) for r in cur.fetchall()]