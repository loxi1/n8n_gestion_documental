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