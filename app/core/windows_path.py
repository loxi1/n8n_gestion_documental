from __future__ import annotations

from datetime import date


MESES_ES = {
    1: "ENERO",
    2: "FEBRERO",
    3: "MARZO",
    4: "ABRIL",
    5: "MAYO",
    6: "JUNIO",
    7: "JULIO",
    8: "AGOSTO",
    9: "SEPTIEMBRE",
    10: "OCTUBRE",
    11: "NOVIEMBRE",
    12: "DICIEMBRE",
}


def build_windows_target_path(ruta_base: str, fecha_emision: date | None) -> str | None:
    if not ruta_base or not fecha_emision:
        return None

    mes = MESES_ES[fecha_emision.month]
    return rf"{ruta_base}\{mes}"