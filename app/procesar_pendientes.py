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
from core.grupo_documental import get_next_correlativo_mes
from core.text_utils import normalize_text
from core.windows_path import build_windows_target_path


SQL_SELECT_PENDING = """
SELECT
    d.id AS documento_id,
    d.correo_id,
    d.proveedor_id,
    d.tipo_documental,
    d.serie,
    d.numero,
    d.ruc,
    d.razon_social,
    d.fecha_emision,
    d.estado_documento,
    a.id AS archivo_id,
    a.ruta_temporal,
    a.nombre_archivo_actual,
    a.nombre_archivo_original
FROM documentos d
JOIN archivos a ON a.documento_id = d.id
WHERE d.estado_documento IN ('pendiente', 'no_identificado', 'clasificado', 'error')
ORDER BY d.id ASC;
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


def get_factura_principal_del_correo(correo_id: int) -> dict | None:
    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT
                id,
                grupo_codigo,
                correlativo_mes,
                fecha_emision,
                cliente_destino_id
            FROM documentos
            WHERE correo_id = %s
              AND tipo_documental = 'factura'
            ORDER BY id ASC
            LIMIT 1
            """,
            (correo_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def process_one_document(item: dict) -> None:
    documento_id = item["documento_id"]
    correo_id = item["correo_id"]
    archivo_id = item["archivo_id"]
    ruta_temporal = item["ruta_temporal"]
    nombre_archivo_actual = item["nombre_archivo_actual"]
    nombre_archivo_original = item["nombre_archivo_original"]

    pdf_path = resolve_absolute_path(ruta_temporal)

    if not pdf_path.exists():
        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                "UPDATE documentos SET estado_documento = 'error', actualizado_en = NOW() WHERE id = %s",
                (documento_id,),
            )
            cur.execute(
                "UPDATE archivos SET estado_archivo = 'error', actualizado_en = NOW() WHERE id = %s",
                (archivo_id,),
            )
        print(f"[ERROR] No existe archivo: {pdf_path}")
        return

    text = ""
    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception as exc:
        print(f"[WARN] Error leyendo PDF directo {pdf_path.name}: {exc}")

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

    if not text.strip():
        nuevo_nombre, destino_relativo = move_to_bucket(pdf_path, "no_identificados", nombre_archivo_actual)

        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                SQL_UPDATE_DOCUMENTO,
                {
                    "proveedor_id": None,
                    "cliente_destino_id": None,
                    "tipo_documental": None,
                    "serie": None,
                    "numero": None,
                    "ruc": None,
                    "razon_social": None,
                    "fecha_emision": None,
                    "importe": None,
                    "estado_documento": "no_identificado",
                    "grupo_codigo": None,
                    "correlativo_mes": None,
                    "es_principal": False,
                    "documento_principal_id": None,
                    "nombre_final": None,
                    "ruta_windows_final": None,
                    "documento_id": documento_id,
                },
            )
            cur.execute(
                SQL_UPDATE_ARCHIVO,
                {
                    "nombre_archivo_actual": nuevo_nombre,
                    "ruta_temporal": destino_relativo,
                    "estado_archivo": "error",
                    "archivo_id": archivo_id,
                },
            )

        print(f"[WARN] No identificado: documento_id={documento_id} archivo={pdf_path.name}")
        return

    fields = extract_basic_fields(text, nombre_archivo_original)
    tipo_documental = fields["tipo_documental"]
    fecha_emision_normalizada = normalize_date(fields["fecha_emision"])
    fecha_emision_date = parse_iso_date(fecha_emision_normalizada)

    cliente_raw = extract_cliente_destino_raw(text)
    cliente_match = find_cliente_destino_by_alias(cliente_raw)

    ruc_emisor = fields["ruc"]
    razon_social_emisor = item.get("razon_social") or None

    # Si aún no tienes razon_social bien extraída, por ahora toma algo provisional
    if not razon_social_emisor:
        # intenta EMISOR o proveedor visual
        m = re.search(r"\bEMISOR[:\s]+(.+?)(?:\bDIRECCION\b|\bRUC\b)", normalize_text(text), re.IGNORECASE | re.DOTALL)
        if m:
            razon_social_emisor = m.group(1).strip()
        else:
            razon_social_emisor = "SIN_RAZON_SOCIAL"

    proveedor_id = get_or_create_proveedor(ruc_emisor, razon_social_emisor)

    grupo_codigo = None
    correlativo_mes = None
    es_principal = False
    documento_principal_id = None
    cliente_destino_id = cliente_match["id"] if cliente_match else None
    ruta_windows_final = None

    if tipo_documental == "factura" and fecha_emision_date:
        correlativo_mes, grupo_codigo = get_next_correlativo_mes(fecha_emision_date, prefijo="04")
        es_principal = True
        documento_principal_id = None

        if cliente_match:
            ruta_windows_final = build_windows_target_path(cliente_match["ruta_windows"], fecha_emision_date)

    else:
        factura_principal = get_factura_principal_del_correo(correo_id)
        if factura_principal:
            grupo_codigo = factura_principal.get("grupo_codigo")
            correlativo_mes = factura_principal.get("correlativo_mes")
            documento_principal_id = factura_principal.get("id")
            if not cliente_destino_id:
                cliente_destino_id = factura_principal.get("cliente_destino_id")

    estado_documento = "clasificado" if tipo_documental != "otro" else "no_identificado"

    nombre_final = None
    if grupo_codigo:
        nombre_final = build_final_name(
            grupo_codigo=grupo_codigo,
            serie=fields["serie"],
            numero=fields["numero"],
            ruc_emisor=ruc_emisor,
            razon_social_emisor=razon_social_emisor,
            tipo_documental=tipo_documental,
            fallback_name=nombre_archivo_actual,
        )

    year = pdf_path.parent.parent.name
    month = pdf_path.parent.name
    bucket = "pendientes_clasificados" if estado_documento == "clasificado" else "no_identificados"
    destino_nombre = nombre_final or nombre_archivo_actual
    destino_relativo = f"{bucket}/{year}/{month}/{destino_nombre}"
    destino_abs = STORAGE_DIR / destino_relativo

    move_file(pdf_path, destino_abs)

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            SQL_UPDATE_DOCUMENTO,
            {
                "proveedor_id": proveedor_id,
                "cliente_destino_id": cliente_destino_id,
                "tipo_documental": tipo_documental,
                "serie": fields["serie"],
                "numero": fields["numero"],
                "ruc": ruc_emisor,
                "razon_social": razon_social_emisor,
                "fecha_emision": fecha_emision_normalizada,
                "importe": fields["importe"],
                "estado_documento": estado_documento,
                "grupo_codigo": grupo_codigo,
                "correlativo_mes": correlativo_mes,
                "es_principal": es_principal,
                "documento_principal_id": documento_principal_id,
                "nombre_final": nombre_final,
                "ruta_windows_final": ruta_windows_final,
                "documento_id": documento_id,
            },
        )
        cur.execute(
            SQL_UPDATE_ARCHIVO,
            {
                "nombre_archivo_actual": destino_nombre,
                "ruta_temporal": destino_relativo,
                "estado_archivo": "renombrado",
                "archivo_id": archivo_id,
            },
        )

    print(
        f"[OK] documento_id={documento_id} tipo={tipo_documental} "
        f"grupo={grupo_codigo} nombre={destino_nombre}"
    )

def select_factura_principal(documentos: list[dict]) -> dict | None:
    facturas = [d for d in documentos if d.get("tipo_documental") == "factura"]

    if not facturas:
        return None

    # prioridad: factura con fecha + serie F*
    facturas.sort(
        key=lambda d: (
            0 if d.get("fecha_emision") else 1,
            0 if str(d.get("serie") or "").upper().startswith("F") else 1,
            d["documento_id"],
        )
    )
    return facturas[0]


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