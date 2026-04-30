from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime, date
from pathlib import Path

import requests

from core.config import STORAGE_DIR, OCR_TMP_DIR, APISPERU_TOKEN, DEV_FORCE_REVIEW_FACTURAS
from core.db import get_cursor
from core.extractor_pdf import extract_text_from_pdf
from core.classifier import extract_basic_fields
from core.file_manager import build_final_name, move_file
from core.clientes_destino import extract_cliente_destino_raw, find_cliente_destino_by_alias
from core.grupo_documental import get_next_correlativo_mes, select_factura_principal
from core.text_utils import normalize_text
from core.windows_path import build_windows_target_path
from core.qr_reader import decode_qr_from_pdf
from core.qr_parser import parse_qr_payload


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
    igv = %(igv)s,
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
        "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
        "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
        "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
    }

    # 21/04/2026
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if m:
        day, mon, year = m.groups()
        return f"{year}-{mon}-{day}"

    # 2026-04-16
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        return raw

    # 14-04-2026
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", raw)
    if m:
        day, mon, year = m.groups()
        return f"{year}-{mon}-{day}"

    # 14-ABR-2026
    m = re.match(r"^(\d{1,2})-([A-Z]{3})-(\d{4})$", raw)
    if m:
        day, mon_txt, year = m.groups()
        mon = meses.get(mon_txt)
        if mon:
            return f"{year}-{mon}-{str(day).zfill(2)}"

    # CALLAO, 21 DE ABRIL DEL 2026
    m = re.search(r"(\d{1,2}) DE ([A-ZÁÉÍÓÚ]+) DEL (\d{4})", raw)
    if m:
        day, mon_txt, year = m.groups()
        mon_txt = (
            mon_txt.replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )
        mon = meses.get(mon_txt)
        if mon:
            return f"{year}-{mon}-{str(day).zfill(2)}"

    return None


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_amount(value: str | None) -> float | None:
    if not value:
        return None

    raw = str(value).strip().replace(" ", "")

    if "," in raw and "." in raw:
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) in (2, 3):
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")

    raw = re.sub(r"[^0-9.\-]", "", raw)

    try:
        return float(raw)
    except:
        return None


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


def update_correo_estado(correo_id: int, procesado: bool, estado_correo: str, observacion: str | None = None) -> None:
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
    qr_data = None

    try:
        text = extract_text_from_pdf(pdf_path)
    except Exception:
        text = ""

    # 1. Intentar QR real directamente del PDF
    qr_candidates = decode_qr_from_pdf(pdf_path)
    for candidate in qr_candidates:
        parsed = parse_qr_payload(candidate)
        if parsed:
            qr_data = parsed
            break

    # 2. Si no hay texto útil, hacer OCR
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

            # 3. Si aún no hay QR, intentar desde OCR PDF
            if not qr_data:
                pdf_path = resolve_absolute_path(doc["ruta_temporal"])
                qr_candidates = decode_qr_from_pdf(pdf_path)
                for candidate in qr_candidates:
                    parsed = parse_qr_payload(candidate)
                    if parsed:
                        qr_data = parsed
                        break

    fields = extract_basic_fields(text, item["nombre_archivo_original"])

    qr_data = fields.get("qr_data")

    def should_use_qr(fields: dict) -> bool:
    tipo = fields.get("tipo_documental")

    if tipo not in ("factura", "guia_remision"):
        return False

    return (
        not fields.get("serie")
        or not fields.get("numero")
        or not fields.get("ruc")
        or not fields.get("fecha_emision")
        or (tipo == "factura" and not fields.get("importe"))
    )


def enrich_document(item: dict) -> dict:
    pdf_path = resolve_absolute_path(item["ruta_temporal"])
    text = ""
    ocr_output = None
    qr_data = None

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

    # QR solo para factura / guía y solo si falta data
    if should_use_qr(fields):
        qr_candidates = decode_qr_from_pdf(pdf_path, max_pages=1, dpi=280)

        # fallback: si hubo OCR PDF, también intentar ahí
        if not qr_candidates and ocr_output and ocr_output.exists():
            qr_candidates = decode_qr_from_pdf(ocr_output, max_pages=1, dpi=280)

        for candidate in qr_candidates:
            parsed = parse_qr_payload(candidate)

            if not parsed:
                continue

            if parsed.get("tipo_documental") != fields.get("tipo_documental"):
                continue

            qr_data = parsed
            fields["qr_data"] = parsed
            fields["serie"] = fields.get("serie") or parsed.get("serie")
            fields["numero"] = fields.get("numero") or parsed.get("numero")
            fields["ruc"] = fields.get("ruc") or parsed.get("ruc_emisor")
            fields["fecha_emision"] = fields.get("fecha_emision") or parsed.get("fecha_emision")
            fields["importe"] = fields.get("importe") or parsed.get("importe")
            fields["igv"] = fields.get("igv") or parsed.get("igv")
            break

    # Si QR real existe, tiene prioridad
    if qr_data:
        fields["tipo_documental"] = qr_data.get("tipo_documental") or fields.get("tipo_documental")
        fields["serie"] = qr_data.get("serie") or fields.get("serie")
        fields["numero"] = qr_data.get("numero") or fields.get("numero")
        fields["ruc"] = qr_data.get("ruc_emisor") or fields.get("ruc")
        fields["fecha_emision"] = qr_data.get("fecha_emision") or fields.get("fecha_emision")
        fields["importe"] = qr_data.get("importe") or fields.get("importe")
        fields["igv"] = qr_data.get("igv") or fields.get("igv")

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
        "qr_data": qr_data,
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
                    igv = %(igv)s,
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
                    "importe": normalize_amount(fields.get("importe")),
                    "igv": normalize_amount(fields.get("igv")),
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


def is_factura_valida_produccion(
    fields: dict,
    qr_data: dict | None,
) -> tuple[bool, list[str], list[str]]:
    """
    Valida factura usando:
    1. QR (fuente principal)
    2. Texto OCR (fallback)

    Retorna:
    (es_valida, diferencias_criticas, advertencias)
    """

    criticas: list[str] = []
    advertencias: list[str] = []

    tipo = fields.get("tipo_documental")
    serie = fields.get("serie")
    numero = fields.get("numero")
    ruc = fields.get("ruc")
    fecha = normalize_date(fields.get("fecha_emision"))
    importe = normalize_amount(fields.get("importe"))

    # =========================
    # 🧾 CASO 1: QR DISPONIBLE
    # =========================
    if qr_data and qr_data.get("tipo_doc_codigo") == "01":
        qr_serie = qr_data.get("serie")
        qr_numero = qr_data.get("numero")
        qr_ruc = qr_data.get("ruc_emisor")
        qr_fecha = normalize_date(qr_data.get("fecha_emision"))
        qr_importe = normalize_amount(qr_data.get("importe"))

        # 🔴 VALIDACIONES CRÍTICAS
        if tipo and normalize_compare_str(tipo) != "FACTURA":
            criticas.append(f"tipo texto={tipo} QR=factura")

        if not qr_ruc:
            criticas.append("qr sin ruc_emisor")

        if not qr_serie:
            criticas.append("qr sin serie")

        if not qr_numero:
            criticas.append("qr sin numero")

        if not qr_fecha:
            criticas.append("qr sin fecha_emision")

        # 🔴 CRUCE TEXTO vs QR
        if serie and qr_serie and normalize_compare_str(serie) != normalize_compare_str(qr_serie):
            criticas.append(f"serie texto={serie} QR={qr_serie}")

        if numero and qr_numero and normalize_compare_str(numero) != normalize_compare_str(qr_numero):
            criticas.append(f"numero texto={numero} QR={qr_numero}")

        # ⚠️ ADVERTENCIAS (NO BLOQUEAN)
        if ruc and qr_ruc and normalize_compare_str(ruc) != normalize_compare_str(qr_ruc):
            advertencias.append(f"ruc texto={ruc} QR={qr_ruc}")

        if fecha and qr_fecha and normalize_compare_str(fecha) != normalize_compare_str(qr_fecha):
            advertencias.append(f"fecha texto={fecha} QR={qr_fecha}")

        if importe and qr_importe and abs(importe - qr_importe) > 0.1:
            advertencias.append(f"importe texto={importe} QR={qr_importe}")

        return len(criticas) == 0, criticas, advertencias

    # =========================
    # 🧾 CASO 2: SIN QR (OCR)
    # =========================
    if tipo == "factura":
        if not serie:
            criticas.append("factura sin serie")

        if not numero:
            criticas.append("factura sin numero")

        if not ruc:
            criticas.append("factura sin ruc")

        if not fecha:
            criticas.append("factura sin fecha_emision")

        # importe puede ser opcional (algunas facturas OCR fallan)
        if not importe:
            advertencias.append("factura sin importe")

        return len(criticas) == 0, criticas, advertencias

    # =========================
    # ❌ NO ES FACTURA
    # =========================
    criticas.append(f"tipo_documental no es factura: {tipo}")
    return False, criticas, advertencias

def process_correo(items: list[dict]) -> None:
    enriched = [enrich_document(x) for x in items]

    correo_id = items[0]["correo_id"]

    print(f"[DEBUG] correo_id={correo_id} enriquecidos:")
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
            "qr": bool(d.get("qr_data")),
        })

    factura_principal = select_factura_principal(enriched)
    print("[DEBUG] factura_principal =", factura_principal)

    hay_guia_valida = any(
        d["fields"].get("tipo_documental") == "guia_remision"
        and d.get("fecha_emision_date")
        and d["fields"].get("serie")
        and d["fields"].get("numero")
        and d["fields"].get("ruc")
        for d in enriched
    )

    hay_oc_valida = any(
        d["fields"].get("tipo_documental") == "orden_compra"
        and d["fields"].get("numero")
        for d in enriched
    )

    if not factura_principal and not hay_guia_valida and not hay_oc_valida:
        print(f"[WARN] correo_id={correo_id} sin factura, guía ni OC válida")

        mark_documents_as_review(
            items=enriched,
            estado_documento="no_identificado",
            bucket="no_identificados",
        )

        update_correo_estado(
            correo_id=correo_id,
            procesado=False,
            estado_correo="sin_documento_valido",
            observacion="No se encontró factura, guía ni orden de compra válida.",
        )
        return

    fecha_principal = factura_principal.get("fecha_emision_date") if factura_principal else None

    if factura_principal and not fecha_principal:
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

    fecha_grupo_base = fecha_principal

    if not fecha_grupo_base:
        for d in enriched:
            if (
                d["fields"].get("tipo_documental") == "guia_remision"
                and d.get("fecha_emision_date")
            ):
                fecha_grupo_base = d["fecha_emision_date"]
                break

    if not fecha_grupo_base:
        fecha_grupo_base = datetime.now().date()

    correlativo_mes_global, grupo_codigo_global = get_next_correlativo_mes(
        fecha_grupo_base,
        prefijo="04",
    )

    documento_principal_id = factura_principal["documento_id"] if factura_principal else None

    cliente_match = factura_principal.get("cliente_match") if factura_principal else None
    cliente_destino_id_global = cliente_match["id"] if cliente_match else None

    ruta_windows_final_global = None
    if cliente_match:
        ruta_windows_final_global = build_windows_target_path(
            cliente_match["ruta_windows"],
            fecha_grupo_base,
        )

    total_docs = len(enriched)
    total_clasificados = 0
    total_no_identificados = 0
    total_adjuntos_factura = 0
    total_revision_manual = 0

    for doc in enriched:
        fields = doc["fields"]
        tipo_documental = fields["tipo_documental"]
        qr_data = doc.get("qr_data")

        es_documento_valido, diferencias_criticas, advertencias = is_documento_valido_produccion(
            fields,
            qr_data,
        )

        ruc_emisor = fields["ruc"]
        razon_social_emisor = doc["razon_social_emisor_detectada"] or "SIN_RAZON_SOCIAL"

        proveedor = get_or_create_proveedor(ruc_emisor, razon_social_emisor)
        proveedor_id = proveedor["id"] if proveedor else None

        if proveedor and proveedor.get("nombre"):
            razon_social_emisor = proveedor["nombre"]

        es_principal = (
            doc["documento_id"] == documento_principal_id
            if documento_principal_id
            else tipo_documental in ("factura", "guia_remision", "orden_compra")
        )

        documento_principal_ref = None if es_principal else documento_principal_id

        cliente_id_final = (
            doc["cliente_match"]["id"]
            if doc.get("cliente_match")
            else cliente_destino_id_global
        )

        ruta_windows_final = ruta_windows_final_global

        if (
            factura_principal
            and tipo_documental == "factura"
            and not fields["serie"]
            and not fields["numero"]
            and ruc_emisor
            and factura_principal["fields"]["ruc"] == ruc_emisor
        ):
            tipo_documental = "adjunto_factura"
            total_adjuntos_factura += 1

        grupo_codigo = grupo_codigo_global
        correlativo_mes = correlativo_mes_global
        year = fecha_grupo_base.year
        month = fecha_grupo_base.month

        if tipo_documental == "otro":
            estado_documento = "no_identificado"
            bucket = "no_identificados"
            estado_archivo = "observado"
            total_no_identificados += 1

        elif tipo_documental in ("factura", "guia_remision", "orden_compra"):
            if not es_documento_valido:
                estado_documento = "revision_manual"
                bucket = "pendientes_revision"
                estado_archivo = "observado"
                total_revision_manual += 1
            else:
                estado_documento = "clasificado"
                bucket = "pendientes_clasificados"
                estado_archivo = "renombrado"
                total_clasificados += 1

        else:
            estado_documento = "no_identificado"
            bucket = "no_identificados"
            estado_archivo = "observado"
            total_no_identificados += 1

        prefijo_nombre = None
        ruc_cliente_qr = qr_data.get("num_doc_adquirente") if qr_data else None

        cliente_por_qr = get_cliente_destino_by_ruc(ruc_cliente_qr)

        if cliente_por_qr:
            prefijo_nombre = cliente_por_qr["abreviatura"]
            cliente_id_final = cliente_por_qr["id"]

            if cliente_por_qr.get("ruta_windows"):
                ruta_windows_final = build_windows_target_path(
                    cliente_por_qr["ruta_windows"],
                    fecha_grupo_base,
                )

        elif doc.get("cliente_match"):
            prefijo_nombre = doc["cliente_match"]["abreviatura"]
        else:
            prefijo_nombre = grupo_codigo

        nombre_final = build_final_name(
            grupo_codigo=grupo_codigo,
            tipo_documental=tipo_documental,
            serie=fields["serie"],
            numero=fields["numero"],
            ruc_emisor=ruc_emisor,
            razon_social_emisor=razon_social_emisor,
            fallback_name=doc["nombre_archivo_actual"],
            prefijo_nombre=prefijo_nombre,
        )

        pdf_path = resolve_absolute_path(item["ruta_temporal"])
        destino_relativo = f"{bucket}/{year}/{month:02d}/{nombre_final}"
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
                    "importe": normalize_amount(fields["importe"]),
                    "igv": normalize_amount(fields.get("igv")),
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
                    "estado_archivo": estado_archivo,
                    "archivo_id": doc["archivo_id"],
                },
            )

        ocr_output_path = doc.get("ocr_output_path")
        if ocr_output_path:
            try:
                Path(ocr_output_path).unlink(missing_ok=True)
            except Exception as e:
                print(f"[WARN] no se pudo eliminar OCR temporal: {ocr_output_path} -> {e}")

        if diferencias_criticas:
            print(
                f"[WARN] doc={doc['documento_id']} diferencias críticas: "
                + " | ".join(diferencias_criticas)
            )

        if advertencias:
            print(
                f"[INFO] doc={doc['documento_id']} advertencias: "
                + " | ".join(advertencias)
            )

        print(
            f"[OK] correo={doc['correo_id']} "
            f"doc={doc['documento_id']} "
            f"tipo={tipo_documental} "
            f"estado={estado_documento} "
            f"grupo={grupo_codigo} "
            f"nombre={nombre_final}"
        )

    observacion = (
        f"Procesado correctamente. "
        f"Documentos: {total_docs}, "
        f"clasificados: {total_clasificados}, "
        f"revision_manual: {total_revision_manual}, "
        f"no_identificados: {total_no_identificados}, "
        f"adjuntos_factura: {total_adjuntos_factura}, "
        f"grupo: {grupo_codigo_global}."
    )

    estado_correo = "procesado"
    if total_no_identificados > 0 or total_revision_manual > 0:
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

def normalize_compare_str(value: str | None) -> str:
    if not value:
        return ""
    return normalize_text(value).replace(" ", "").upper()


def normalize_compare_amount(value: str | None) -> str:
    if not value:
        return ""
    raw = normalize_amount(value)
    return raw or ""


def is_guia_valida_produccion(
    fields: dict,
    qr_data: dict | None,
) -> tuple[bool, list[str], list[str]]:
    criticas: list[str] = []
    advertencias: list[str] = []

    tipo = fields.get("tipo_documental")
    serie = fields.get("serie")
    numero = fields.get("numero")
    ruc = fields.get("ruc")
    fecha = normalize_date(fields.get("fecha_emision"))

    if qr_data and qr_data.get("tipo_doc_codigo") == "09":
        qr_serie = qr_data.get("serie")
        qr_numero = qr_data.get("numero")
        qr_ruc = qr_data.get("ruc_emisor")
        qr_fecha = normalize_date(qr_data.get("fecha_emision"))

        if tipo and normalize_compare_str(tipo) != "GUIA_REMISION":
            criticas.append(f"tipo texto={tipo} QR=guia_remision")

        if serie and qr_serie and normalize_compare_str(serie) != normalize_compare_str(qr_serie):
            criticas.append(f"serie texto={serie} QR={qr_serie}")

        if numero and qr_numero and normalize_compare_str(numero) != normalize_compare_str(qr_numero):
            criticas.append(f"numero texto={numero} QR={qr_numero}")

        if ruc and qr_ruc and normalize_compare_str(ruc) != normalize_compare_str(qr_ruc):
            advertencias.append(f"ruc texto={ruc} QR={qr_ruc}")

        if fecha and qr_fecha and normalize_compare_str(fecha) != normalize_compare_str(qr_fecha):
            advertencias.append(f"fecha texto={fecha} QR={qr_fecha}")

        if not qr_ruc:
            criticas.append("qr guia sin ruc_emisor")
        if not qr_serie:
            criticas.append("qr guia sin serie")
        if not qr_numero:
            criticas.append("qr guia sin numero")
        if not qr_fecha:
            criticas.append("qr guia sin fecha_emision")

        return len(criticas) == 0, criticas, advertencias

    if tipo == "guia_remision":
        if not serie:
            criticas.append("guia sin serie")
        if not numero:
            criticas.append("guia sin numero")
        if not ruc:
            criticas.append("guia sin ruc")
        if not fecha:
            criticas.append("guia sin fecha_emision")

        return len(criticas) == 0, criticas, advertencias

    criticas.append(f"tipo_documental no es guia_remision: {tipo}")
    return False, criticas, advertencias

def is_documento_valido_produccion(fields, qr_data):
    tipo = fields.get("tipo_documental")

    if tipo == "factura":
        return is_factura_valida_produccion(fields, qr_data)

    if tipo == "guia_remision":
        return fields.get("serie") and fields.get("numero") and fields.get("ruc"), [], []

    if tipo == "orden_compra":
        return fields.get("numero") is not None, [], []

    return False, [], []

def get_cliente_destino_by_ruc(ruc: str | None) -> dict | None:
    if not ruc:
        return None

    with get_cursor(commit=False) as (_, cur):
        cur.execute(
            """
            SELECT id, nombre_oficial, abreviatura, ruta_windows
            FROM clientes_destino
            WHERE ruc = %(ruc)s
            LIMIT 1
            """,
            {"ruc": ruc},
        )
        return cur.fetchone()

def should_use_qr(fields: dict) -> bool:
    tipo = fields.get("tipo_documental")

    if tipo not in ("factura", "guia_remision"):
        return False

    if not fields.get("serie"):
        return True

    if not fields.get("numero"):
        return True

    if not fields.get("ruc"):
        return True

    if tipo == "factura" and not fields.get("fecha_emision"):
        return True

    if tipo == "factura" and not fields.get("importe"):
        return True

    return False

if __name__ == "__main__":
    main()