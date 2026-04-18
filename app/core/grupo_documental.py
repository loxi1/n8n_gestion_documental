from __future__ import annotations

import re
from datetime import date
from typing import Any

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
                d.proveedor_id,
                d.cliente_destino_id,
                d.tipo_documental,
                d.serie,
                d.numero,
                d.ruc,
                d.razon_social,
                d.fecha_emision,
                d.importe,
                d.estado_documento,
                d.grupo_codigo,
                d.correlativo_mes,
                d.es_principal,
                d.documento_principal_id,
                d.nombre_final,
                d.ruta_windows_final,
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


def extract_oc(text: str) -> str | None:
    patrones = [
        r"\bORDEN DE COMPRA[:\sN°º]*([0-9]{3,})\b",
        r"\bN[°º]\s*OC[:\s]*([0-9]{3,})\b",
        r"\bOC[:\s]*([0-9]{3,})\b",
    ]
    text_u = text.upper()
    for patron in patrones:
        m = re.search(patron, text_u, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def build_operation_key(
    correo_id: int,
    tipo_documental: str | None,
    ruc: str | None,
    oc: str | None,
    cliente_destino_id: int | None,
) -> str:
    """
    Clave lógica de agrupación.
    - Si hay OC, usarla.
    - Si no, usar factura + ruc.
    """
    ruc_txt = (ruc or "SINRUC").strip()
    cli_txt = str(cliente_destino_id or "SINCLI")
    oc_txt = (oc or "").strip()

    if oc_txt:
        return f"{correo_id}|OC|{oc_txt}|{ruc_txt}|{cli_txt}"

    return f"{correo_id}|DOC|{tipo_documental or 'SIN_TIPO'}|{ruc_txt}|{cli_txt}"


def select_factura_principal(items: list[dict]) -> dict | None:
    facturas = [x for x in items if x["fields"]["tipo_documental"] == "factura"]
    if not facturas:
        return None

    # Preferir la que tenga OC y cliente destino
    facturas.sort(
        key=lambda x: (
            0 if x["fields"].get("oc") else 1,
            0 if x.get("cliente_match") else 1,
            0 if x["fields"].get("serie") else 1,
        )
    )
    return facturas[0]