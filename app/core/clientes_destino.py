from __future__ import annotations

import re
from typing import Any

from core.db import get_cursor
from core.text_utils import normalize_text


def extract_cliente_destino_raw(text: str) -> str | None:
    text_u = normalize_text(text)

    patrones = [
        r"\bCLIENTE[:\s]+(.+?)(?:\bRUC\b|\bRUC/DOC\b|\bDIRECCION\b|\bDIRECCION:|\bVENDEDOR\b|\bMONEDA\b)",
        r"\bDESTINATARIO[:\s]+(.+?)(?:\bRUC\b|\bCARGA\b|\bPESO\b|\bCANTIDAD\b)",
        r"\bSEÑOR\(ES\)[:\s]+(.+?)(?:\bFECHA\b|\bR\.U\.C\b|\bRUC\b|\bATENCION\b)",
    ]

    for patron in patrones:
        m = re.search(patron, text_u, re.IGNORECASE | re.DOTALL)
        if m:
            value = m.group(1).strip(" -:")
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                return value

    return None


def find_cliente_destino_by_alias(cliente_raw: str | None) -> dict[str, Any] | None:
    if not cliente_raw:
        return None

    cliente_norm = normalize_text(cliente_raw)

    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT
                c.id,
                c.nombre_oficial,
                c.abreviatura,
                c.ruta_windows,
                a.alias
            FROM clientes_destino_alias a
            JOIN clientes_destino c ON c.id = a.cliente_destino_id
            WHERE c.estado = TRUE
              AND a.estado = TRUE
            """
        )
        rows = cur.fetchall()

    for row in rows:
        alias_norm = normalize_text(row["alias"])
        if alias_norm and alias_norm in cliente_norm:
            return dict(row)

    for row in rows:
        alias_norm = normalize_text(row["alias"])
        if alias_norm and cliente_norm in alias_norm:
            return dict(row)

    return None