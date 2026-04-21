from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime, date
from pathlib import Path

import requests

from core.config import STORAGE_DIR, OCR_TMP_DIR, APISPERU_TOKEN
from core.db import get_cursor
from core.extractor_pdf import extract_text_from_pdf
from core.classifier import extract_basic_fields
from core.file_manager import build_final_name, move_file
from core.clientes_destino import extract_cliente_destino_raw, find_cliente_destino_by_alias
from core.grupo_documental import get_next_correlativo_mes, select_factura_principal
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
WHERE d.estado_documento IN ('pendiente', 'error')
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

SQL_UPDATE_CORREO = """
UPDATE correos_ingresados
SET
    procesado = %(procesado)s,
    estado_correo = %(estado_correo)s,
    observacion = %(observacion)s,
    actualizado_en = NOW()
WHERE id = %(correo_id)s;
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

    meses_largos = {
        "ENERO": "01",
        "FEBRERO": "02",
        "MARZO": "03",
        "ABRIL": "04",
        "MAYO": "05",
        "JUNIO": "06",
        "JULIO": "07",
        "AGOSTO": "08",
        "SEPTIEMBRE": "09",
        "OCTUBRE": "10",
        "NOVIEMBRE": "11",
        "DICIEMBRE": "12",
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

    m = re.match(r"^(\d{1,2}) DE ([A-ZÁÉÍÓÚ]+) DEL (\d{4})$", raw)
    if m:
        day, mon_txt, year = m.groups()
        mon_txt = (
            mon_txt.replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )
        mon = meses_largos.get(mon_txt)
        if mon:
            return f"{year}-{mon}-{str(day).zfill(2)}"

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


def fetch_proveedor_from_api(ruc: str) -> dict | None:
    if not ruc or not APISPERU_TOKEN:
        return None

    url = f"https://dniruc.apisperu.com/api/v1/ruc/{ruc}?token={APISPERU_TOKEN}"

    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "ruc": data.get("ruc"),
            "nombre": data.get("razonSocial"),
            "direccion": data.get("direccion"),
        }
    except Exception as exc:
        print(f"[API RUC ERROR] ruc={ruc} error={exc}")
        return None


def get_or_create_proveedor(
    ruc: str | None,
    razon_social: str | None = None,
    direccion: str | None = None,
) -> dict | None:
    if not ruc:
        return None

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            "SELECT id, ruc, nombre, direccion FROM proveedores WHERE ruc = %s",
            (ruc,),
        )
        row = cur.fetchone()
        if row:
            return dict(row)

    api_data = fetch_proveedor_from_api(ruc)

    nombre_final = api_data.get("nombre") if api_data else (razon_social or "SIN_RAZON_SOCIAL")
    direccion_final = api_data.get("direccion") if api_data else direccion

    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            """
            INSERT INTO proveedores (ruc, nombre, direccion, creado_en, actualizado_en)
            VALUES (%s, %s, %s, NOW(), NOW())
            RETURNING id, ruc, nombre, direccion
            """,
            (ruc, nombre_final, direccion_final),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_correo_estado(
    correo_id: int,
    procesado: bool,
    estado_correo: str,
    observacion: str | None = None,
) -> None:
    with get_cursor(commit=True) as (_, cur):
        cur.execute(
            SQL_UPDATE_CORREO,
            {
                "correo_id": correo_id,
                "procesado": procesado,
                "estado_correo": estado_correo,
                "observacion": observacion,
            },
        )


def get_pending_rows():
    with get_cursor() as (_, cur):
        cur.execute(SQL_SELECT_PENDING)
        return [dict(r) for r in cur.fetchall()]


def group_by_correo(rows: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["correo_id"], []).append(row)
    return grouped


def enrich_document(item: dict) -> dict:
    pdf_path = resolve_absolute_path(item["ruta_temporal"])
    text = ""
    ocr_output = None

    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception:
        text = ""

    if not text.strip():
        year = pdf_path.parent.parent.name
        month = pdf_path.parent.name
        ocr_output = OCR_TMP_DIR / year / month / f"ocr_{pdf_path.name}"
        ocr_ok = run_ocr(pdf_path, ocr_output)
        if ocr_ok and ocr_output.exists():
            try:
                text = extract_text_from_pdf(ocr_output)
            except Exception:
                text = ""

    fields = extract_basic_fields(text, item["nombre_archivo_original"])
    cliente_raw = extract_cliente_destino_raw(text)
    cliente_match = find_cliente_destino_by_alias(cliente_raw)
    fecha_norm = normalize_date(fields["fecha_emision"])
    fecha_date = parse_iso_date(fecha_norm) if fecha_norm else None

    razon_social_emisor = item.get("razon_social") or None
    if not razon_social_emisor:
        m = re.search(
            r"\bEMISOR[:\s]+(.+?)(?:\bDIRECCION\b|\bRUC\b)",
            normalize_text(text),
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            razon_social_emisor = m.group(1).strip()

    return {
        **item,
        "text": text,
        "fields": fields,
        "cliente_raw": cliente_raw,
        "cliente_match": cliente_match,
        "fecha_emision_norm": fecha_norm,
        "fecha_emision_date": fecha_date,
        "razon_social_emisor_detectada": razon_social_emisor,
        "ocr_output_path": str(ocr_output) if ocr_output and ocr_output.exists() else None,
    }


def mark_documents_as_review(
    items: list[dict],
    estado_documento: str,
    bucket: str = "pendientes_revision",
) -> None:
    for item in items:
        pdf_path = resolve_absolute_path(item["ruta_temporal"])
        file_name = item["nombre_archivo_actual"]

        year = pdf_path.parent.parent.name
        month = pdf_path.parent.name

        destino_relativo = f"{bucket}/{year}/{month}/{file_name}"
        destino_abs = STORAGE_DIR / destino_relativo

        if pdf_path.exists() and pdf_path.resolve() != destino_abs.resolve():
            move_file(pdf_path, destino_abs)

        fields = item.get("fields", {})
        ruc_emisor = fields.get("ruc")
        razon_social_emisor = item.get("razon_social_emisor_detectada") or item.get("razon_social") or "SIN_RAZON_SOCIAL"

        proveedor = get_or_create_proveedor(ruc_emisor, razon_social_emisor)
        proveedor_id = proveedor["id"] if proveedor else None

        if proveedor and proveedor.get("nombre"):
            razon_social_emisor = proveedor["nombre"]

        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                """
                UPDATE documentos
                SET
                    proveedor_id = %(proveedor_id)s,
                    tipo_documental = %(tipo_documental)s,
                    serie = %(serie)s,
                    numero = %(numero)s,
                    ruc = %(ruc)s,
                    razon_social = %(razon_social)s,
                    fecha_emision = %(fecha_emision)s,
                    importe = %(importe)s,
                    estado_documento = %(estado_documento)s,
                    actualizado_en = NOW()
                WHERE id = %(documento_id)s
                """,
                {
                    "proveedor_id": proveedor_id,
                    "tipo_documental": fields.get("tipo_documental"),
                    "serie": fields.get("serie"),
                    "numero": fields.get("numero"),
                    "ruc": ruc_emisor,
                    "razon_social": razon_social_emisor,
                    "fecha_emision": item.get("fecha_emision_norm"),
                    "importe": fields.get("importe"),
                    "estado_documento": estado_documento,
                    "documento_id": item["documento_id"],
                },
            )

            cur.execute(
                SQL_UPDATE_ARCHIVO,
                {
                    "nombre_archivo_actual": file_name,
                    "ruta_temporal": destino_relativo,
                    "estado_archivo": "observado",
                    "archivo_id": item["archivo_id"],
                },
            )


def process_correo(items: list[dict]) -> None:
    enriched = [enrich_document(x) for x in items]

    print(f"[DEBUG] correo_id={items[0]['correo_id']} enriquecidos:")
    for d in enriched:
        print({
            "documento_id": d["documento_id"],
            "archivo": d["nombre_archivo_actual"],
            "tipo": d["fields"]["tipo_documental"],
            "serie": d["fields"]["serie"],
            "numero": d["fields"]["numero"],
            "ruc": d["fields"]["ruc"],
            "oc": d["fields"].get("oc"),
            "cliente_raw": d.get("cliente_raw"),
            "cliente_match": d.get("cliente_match"),
            "fecha": d.get("fecha_emision_norm"),
        })

    factura_principal = select_factura_principal(enriched)
    print("[DEBUG] factura_principal =", factura_principal)

    correo_id = items[0]["correo_id"]

    if not factura_principal:
        print(f"[WARN] correo_id={correo_id} sin factura principal")
        mark_documents_as_review(
            items=enriched,
            estado_documento="pendiente_asociacion",
            bucket="pendientes_revision",
        )
        update_correo_estado(
            correo_id=correo_id,
            procesado=False,
            estado_correo="sin_factura_principal",
            observacion="No se encontró factura principal en el correo.",
        )
        return

    fecha_principal = factura_principal.get("fecha_emision_date")
    if not fecha_principal:
        print(f"[WARN] correo_id={correo_id} factura sin fecha")
        mark_documents_as_review(
            items=enriched,
            estado_documento="revision_manual",
            bucket="pendientes_revision",
        )
        update_correo_estado(
            correo_id=correo_id,
            procesado=False,
            estado_correo="factura_sin_fecha",
            observacion="La factura principal no tiene fecha de emisión reconocible.",
        )
        return

    correlativo_mes, grupo_codigo = get_next_correlativo_mes(fecha_principal, prefijo="04")

    cliente_match = factura_principal.get("cliente_match")
    cliente_destino_id = cliente_match["id"] if cliente_match else None

    ruta_windows_final = None
    if cliente_match:
        ruta_windows_final = build_windows_target_path(
            cliente_match["ruta_windows"],
            fecha_principal,
        )

    documento_principal_id = factura_principal["documento_id"]

    total_docs = len(enriched)
    total_clasificados = 0
    total_no_identificados = 0
    total_adjuntos_factura = 0

    for doc in enriched:
        fields = doc["fields"]
        tipo_documental = fields["tipo_documental"]
        ruc_emisor = fields["ruc"]
        razon_social_emisor = doc["razon_social_emisor_detectada"] or "SIN_RAZON_SOCIAL"

        proveedor = get_or_create_proveedor(ruc_emisor, razon_social_emisor)
        proveedor_id = proveedor["id"] if proveedor else None

        if proveedor and proveedor.get("nombre"):
            razon_social_emisor = proveedor["nombre"]

        es_principal = doc["documento_id"] == documento_principal_id
        documento_principal_ref = None if es_principal else documento_principal_id

        cliente_id_final = (
            doc["cliente_match"]["id"]
            if doc.get("cliente_match")
            else cliente_destino_id
        )

        if (
            tipo_documental == "factura"
            and not fields["serie"]
            and not fields["numero"]
            and ruc_emisor
            and factura_principal["fields"]["ruc"] == ruc_emisor
        ):
            tipo_documental = "adjunto_factura"
            total_adjuntos_factura += 1
            print(f"[DEBUG] doc={doc['documento_id']} reclasificado a ADJUNTO_FACTURA")

        if tipo_documental == "otro":
            tipo_documental = "adjunto_documento"

        nombre_final = build_final_name(
            grupo_codigo=grupo_codigo,
            tipo_documental=tipo_documental,
            serie=fields["serie"],
            numero=fields["numero"],
            ruc_emisor=ruc_emisor,
            razon_social_emisor=razon_social_emisor,
            fallback_name=doc["nombre_archivo_actual"],
        )

        pdf_path = resolve_absolute_path(doc["ruta_temporal"])
        year = pdf_path.parent.parent.name
        month = pdf_path.parent.name

        estado_documento = "clasificado" if tipo_documental != "otro" else "no_identificado"
        bucket = "pendientes_clasificados" if estado_documento == "clasificado" else "no_identificados"

        if estado_documento == "clasificado":
            total_clasificados += 1
        else:
            total_no_identificados += 1

        destino_relativo = f"{bucket}/{year}/{month}/{nombre_final}"
        destino_abs = STORAGE_DIR / destino_relativo

        if pdf_path.exists() and pdf_path.resolve() != destino_abs.resolve():
            move_file(pdf_path, destino_abs)

        with get_cursor(commit=True) as (_, cur):
            cur.execute(
                SQL_UPDATE_DOCUMENTO,
                {
                    "proveedor_id": proveedor_id,
                    "cliente_destino_id": cliente_id_final,
                    "tipo_documental": tipo_documental,
                    "serie": fields["serie"],
                    "numero": fields["numero"],
                    "ruc": ruc_emisor,
                    "razon_social": razon_social_emisor,
                    "fecha_emision": doc["fecha_emision_norm"],
                    "importe": fields["importe"],
                    "estado_documento": estado_documento,
                    "grupo_codigo": grupo_codigo,
                    "correlativo_mes": correlativo_mes,
                    "es_principal": es_principal,
                    "documento_principal_id": documento_principal_ref,
                    "nombre_final": nombre_final,
                    "ruta_windows_final": ruta_windows_final,
                    "documento_id": doc["documento_id"],
                },
            )

            cur.execute(
                SQL_UPDATE_ARCHIVO,
                {
                    "nombre_archivo_actual": nombre_final,
                    "ruta_temporal": destino_relativo,
                    "estado_archivo": "renombrado",
                    "archivo_id": doc["archivo_id"],
                },
            )

        print(
            f"[OK] correo={doc['correo_id']} "
            f"doc={doc['documento_id']} "
            f"tipo={tipo_documental} "
            f"grupo={grupo_codigo} "
            f"nombre={nombre_final}"
        )

    observacion = (
        f"Procesado correctamente. "
        f"Documentos: {total_docs}, "
        f"clasificados: {total_clasificados}, "
        f"no_identificados: {total_no_identificados}, "
        f"adjuntos_factura: {total_adjuntos_factura}, "
        f"grupo: {grupo_codigo}."
    )

    estado_correo = "procesado"
    if total_no_identificados > 0:
        estado_correo = "procesado_con_observaciones"

    update_correo_estado(
        correo_id=correo_id,
        procesado=True,
        estado_correo=estado_correo,
        observacion=observacion,
    )


def main() -> None:
    rows = get_pending_rows()
    if not rows:
        print("No hay documentos pendientes.")
        return

    grouped = group_by_correo(rows)
    print(f"Correos pendientes encontrados: {len(grouped)}")

    for correo_id, items in grouped.items():
        print(f"[INFO] procesando correo_id={correo_id} documentos={len(items)}")
        process_correo(items)


if __name__ == "__main__":
    main()