from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime, date
from pathlib import Path

from core.config import STORAGE_DIR, OCR_TMP_DIR
from core.db import get_cursor
from core.extractor_pdf import extract_text_from_pdf
from core.classifier import extract_basic_fields
from core.file_manager import build_final_name, move_file
from core.clientes_destino import extract_cliente_destino_raw, find_cliente_destino_by_alias
from core.grupo_documental import (
    get_next_correlativo_mes,
    get_documentos_por_correo,
    extract_oc,
    build_operation_key,
    select_factura_principal,
)
from core.text_utils import normalize_text
from core.windows_path import build_windows_target_path


SQL_SELECT_CORREOS_PENDIENTES = """
SELECT DISTINCT correo_id
FROM documentos
WHERE estado_documento IN ('pendiente', 'no_identificado', 'clasificado', 'error')
  AND correo_id IS NOT NULL
ORDER BY correo_id;
"""

SQL_UPDATE_DOCUMENTO = """
UPDATE documentos
SET
    proveedor_id = %(proveedor_id)s,
    cliente_destino_id = %(cliente_destino_id)s,
    tipo_documental = %(tipo_documental)s,
    serie = %(serie)s,
    numero = %(numero)s,
    ruc = %(ruc)s,
    razon_social = %(razon_social)s,
    fecha_emision = %(fecha_emision)s,
    importe = %(importe)s,
    estado_documento = %(estado_documento)s,
    grupo_codigo = %(grupo_codigo)s,
    correlativo_mes = %(correlativo_mes)s,
    es_principal = %(es_principal)s,
    documento_principal_id = %(documento_principal_id)s,
    nombre_final = %(nombre_final)s,
    ruta_windows_final = %(ruta_windows_final)s,
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
    raw = str(path.resolve()).replace("\\", "/")
    if len(raw) >= 2 and raw[1] == ":":
        drive = raw[0].lower()
        rest = raw[2:]
        return f"/mnt/{drive}{rest}"
    return raw


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None

    raw = value.strip().upper()
    meses = {
        "ENE": "01", "FEB": "02", "MAR": "03", "ABR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AGO": "08",
        "SEP": "09", "OCT": "10", "NOV": "11", "DIC": "12",
    }

    m = re.match(r"^(\d{2})-([A-Z]{3})-(\d{4})$", raw)
    if m:
        day, mon_txt, year = m.groups()
        mon = meses.get(mon_txt)
        if mon:
            return f"{year}-{mon}-{day}"

    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if m:
        day, mon, year = m.groups()
        return f"{year}-{mon}-{day}"

    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", raw)
    if m:
        day, mon, year = m.groups()
        return f"{year}-{mon}-{day}"

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        return raw

    return None


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def run_ocr(input_pdf: Path, output_pdf: Path) -> bool:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    system_name = platform.system().lower()

    if "windows" in system_name:
        input_wsl = to_wsl_path(input_pdf)
        output_wsl = to_wsl_path(output_pdf)
        cmd = [
            "C:\\Windows\\System32\\wsl.exe",
            "bash",
            "-lc",
            f'/home/loxi1/venvs/ocrpdf/bin/ocrmypdf -l spa --force-ocr "{input_wsl}" "{output_wsl}"'
        ]
    else:
        cmd = [
            "ocrmypdf",
            "-l", "spa",
            "--force-ocr",
            str(input_pdf),
            str(output_pdf),
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
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


def get_or_create_proveedor(ruc: str | None, razon_social: str | None) -> int | None:
    if not ruc:
        return None

    with get_cursor(commit=True) as (_, cur):
        cur.execute("SELECT id FROM proveedores WHERE ruc = %s", (ruc,))
        row = cur.fetchone()
        if row:
            return int(row["id"])

        cur.execute(
            """
            INSERT INTO proveedores (ruc, nombre, creado_en, actualizado_en)
            VALUES (%s, %s, NOW(), NOW())
            RETURNING id
            """,
            (ruc, razon_social),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None


def try_extract_razon_social(text: str, fallback: str | None = None) -> str:
    text_n = normalize_text(text)

    patrones = [
        r"\bEMISOR[:\s]+(.+?)(?:\bDIRECCION\b|\bRUC\b)",
        r"\b^([A-Z0-9 .,&-]{5,})\b.*?\bRUC[:\s]",
    ]

    for patron in patrones:
        m = re.search(patron, text_n, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" -:")
            if value:
                return value

    return fallback or "SIN_RAZON_SOCIAL"


def move_to_bucket(pdf_path: Path, bucket: str, file_name: str) -> str:
    year = pdf_path.parent.parent.name
    month = pdf_path.parent.name
    destino_relativo = f"{bucket}/{year}/{month}/{file_name}"
    destino_abs = STORAGE_DIR / destino_relativo

    if pdf_path.exists() and pdf_path.name != file_name:
        move_file(pdf_path, destino_abs)

    return destino_relativo


def process_one_document(item: dict) -> dict | None:
    documento_id = item["documento_id"]
    archivo_id = item["archivo_id"]
    correo_id = item["correo_id"]
    ruta_temporal = item["ruta_temporal"]
    nombre_archivo_actual = item["nombre_archivo_actual"]
    nombre_archivo_original = item["nombre_archivo_original"]

    pdf_path = resolve_absolute_path(ruta_temporal)
    if not pdf_path.exists():
        print(f"[ERROR] No existe archivo: {pdf_path}")
        return None

    text = ""
    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as exc:
        print(f"[WARN] Error leyendo PDF directo {pdf_path.name}: {exc}")

    if not text.strip():
        year = pdf_path.parent.parent.name
        month = pdf_path.parent.name
        ocr_output = OCR_TMP_DIR / year / month / f"ocr_{pdf_path.name}"

        if run_ocr(pdf_path, ocr_output) and ocr_output.exists():
            try:
                text = extract_text_from_pdf(ocr_output)
                if text.strip():
                    print(f"[OCR OK] documento_id={documento_id} archivo={pdf_path.name}")
            except Exception as exc:
                print(f"[OCR READ ERROR] {exc}")

    if not text.strip():
        return {
            "documento_id": documento_id,
            "archivo_id": archivo_id,
            "correo_id": correo_id,
            "tipo_documental": "otro",
            "serie": None,
            "numero": None,
            "ruc": None,
            "razon_social": "SIN_RAZON_SOCIAL",
            "fecha_emision": None,
            "fecha_emision_date": None,
            "importe": None,
            "cliente_destino_id": None,
            "ruta_windows_final": None,
            "oc": None,
            "operation_key": build_operation_key(correo_id, "otro", None, None, None),
            "estado_documento": "no_identificado",
            "nombre_archivo_actual": nombre_archivo_actual,
            "nombre_archivo_original": nombre_archivo_original,
            "ruta_temporal": ruta_temporal,
            "proveedor_id": None,
        }

    fields = extract_basic_fields(text, nombre_archivo_original)
    tipo_documental = fields["tipo_documental"]
    fecha_emision = normalize_date(fields["fecha_emision"])
    fecha_emision_date = parse_iso_date(fecha_emision)

    cliente_raw = extract_cliente_destino_raw(text)
    cliente_match = find_cliente_destino_by_alias(cliente_raw)
    cliente_destino_id = cliente_match["id"] if cliente_match else None
    ruta_windows_final = None

    if cliente_match and fecha_emision_date:
        ruta_windows_final = build_windows_target_path(cliente_match["ruta_windows"], fecha_emision_date)

    razon_social = try_extract_razon_social(text, item.get("razon_social"))
    ruc = fields["ruc"]
    proveedor_id = get_or_create_proveedor(ruc, razon_social)
    oc = extract_oc(text)

    operation_key = build_operation_key(
        correo_id=correo_id,
        tipo_documental=tipo_documental,
        ruc=ruc,
        oc=oc,
        cliente_destino_id=cliente_destino_id,
    )

    estado_documento = "clasificado" if tipo_documental != "otro" else "no_identificado"

    return {
        "documento_id": documento_id,
        "archivo_id": archivo_id,
        "correo_id": correo_id,
        "tipo_documental": tipo_documental,
        "serie": fields["serie"],
        "numero": fields["numero"],
        "ruc": ruc,
        "razon_social": razon_social,
        "fecha_emision": fecha_emision,
        "fecha_emision_date": fecha_emision_date,
        "importe": fields["importe"],
        "cliente_destino_id": cliente_destino_id,
        "ruta_windows_final": ruta_windows_final,
        "oc": oc,
        "operation_key": operation_key,
        "estado_documento": estado_documento,
        "nombre_archivo_actual": nombre_archivo_actual,
        "nombre_archivo_original": nombre_archivo_original,
        "ruta_temporal": ruta_temporal,
        "proveedor_id": proveedor_id,
    }


def save_processed_document(item: dict) -> None:
    pdf_path = resolve_absolute_path(item["ruta_temporal"])
    bucket = "pendientes_clasificados" if item["estado_documento"] == "clasificado" else "no_identificados"
    destino_relativo = move_to_bucket(pdf_path, bucket, item["nombre_final"])

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            SQL_UPDATE_DOCUMENTO,
            {
                "proveedor_id": item["proveedor_id"],
                "cliente_destino_id": item["cliente_destino_id"],
                "tipo_documental": item["tipo_documental"],
                "serie": item["serie"],
                "numero": item["numero"],
                "ruc": item["ruc"],
                "razon_social": item["razon_social"],
                "fecha_emision": item["fecha_emision"],
                "importe": item["importe"],
                "estado_documento": item["estado_documento"],
                "grupo_codigo": item["grupo_codigo"],
                "correlativo_mes": item["correlativo_mes"],
                "es_principal": item["es_principal"],
                "documento_principal_id": item["documento_principal_id"],
                "nombre_final": item["nombre_final"],
                "ruta_windows_final": item["ruta_windows_final"],
                "documento_id": item["documento_id"],
            },
        )
        cur.execute(
            SQL_UPDATE_ARCHIVO,
            {
                "nombre_archivo_actual": item["nombre_final"],
                "ruta_temporal": destino_relativo,
                "estado_archivo": "renombrado",
                "archivo_id": item["archivo_id"],
            },
        )


def process_correo(correo_id: int) -> None:
    print(f"[CORREO] Procesando correo_id={correo_id}")

    documentos = get_documentos_por_correo(correo_id)
    procesados = []

    for item in documentos:
        data = process_one_document(item)
        if data:
            procesados.append(data)

    if not procesados:
        print(f"[WARN] correo_id={correo_id} sin documentos procesables")
        return

    grupos: dict[str, list[dict]] = {}
    for item in procesados:
        grupos.setdefault(item["operation_key"], []).append(item)

    for _, docs_grupo in grupos.items():
        factura_principal = select_factura_principal(docs_grupo)
        if not factura_principal:
            print(f"[WARN] grupo sin factura principal en correo_id={correo_id}")
            continue

        fecha_emision = factura_principal.get("fecha_emision_date")
        if not fecha_emision:
            print(f"[WARN] factura principal sin fecha en correo_id={correo_id}")
            continue

        correlativo_mes, grupo_codigo = get_next_correlativo_mes(fecha_emision, prefijo="04")
        factura_principal_id = factura_principal["documento_id"]
        cliente_destino_id = factura_principal.get("cliente_destino_id")
        ruta_windows_final = factura_principal.get("ruta_windows_final")

        for item in docs_grupo:
            item["grupo_codigo"] = grupo_codigo
            item["correlativo_mes"] = correlativo_mes
            item["cliente_destino_id"] = item.get("cliente_destino_id") or cliente_destino_id
            item["ruta_windows_final"] = item.get("ruta_windows_final") or ruta_windows_final
            item["es_principal"] = item["documento_id"] == factura_principal_id
            item["documento_principal_id"] = None if item["documento_id"] == factura_principal_id else factura_principal_id
            item["nombre_final"] = build_final_name(
                grupo_codigo=grupo_codigo,
                serie=item.get("serie"),
                numero=item.get("numero"),
                ruc_emisor=item.get("ruc"),
                razon_social_emisor=item.get("razon_social"),
                tipo_documental=item.get("tipo_documental"),
                fallback_name=item.get("nombre_archivo_actual") or item.get("nombre_archivo_original"),
            )
            save_processed_document(item)

        print(f"[OK] correo_id={correo_id} grupo={grupo_codigo} principal={factura_principal_id}")


def get_correos_pendientes() -> list[int]:
    with get_cursor() as (_, cur):
        cur.execute(SQL_SELECT_CORREOS_PENDIENTES)
        rows = cur.fetchall()
        return [int(r["correo_id"]) for r in rows]


def main() -> None:
    correos = get_correos_pendientes()
    if not correos:
        print("No hay correos pendientes.")
        return

    print(f"Correos encontrados: {len(correos)}")
    for correo_id in correos:
        process_correo(correo_id)


if __name__ == "__main__":
    main()