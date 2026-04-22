from pathlib import Path
import pprint

from core.extractor_pdf import extract_text_from_pdf
from core.classifier import detect_tipo_documental, extract_basic_fields
from core.text_utils import normalize_text
from core.qr_parser import extract_qr_candidates, parse_qr_payload
from procesar_pendientes import normalize_date, parse_iso_date


def main() -> None:
    pdf_path = Path(
        r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\files\pendientes_revision\2026\04\posible_documento_20260421233118813_DB9PR05MB10250CA7096BC22409239E8A5BA2C2__1.pdf"
    )

    if not pdf_path.exists():
        print(f"[ERROR] No existe el archivo: {pdf_path}")
        return

    file_name = pdf_path.name

    print("=" * 90)
    print("ARCHIVO:", file_name)
    print("RUTA:", pdf_path)
    print("=" * 90)

    text = extract_text_from_pdf(pdf_path)

    print("\n--- PRIMEROS 3000 CARACTERES DEL TEXTO ---\n")
    print(text[:3000])

    print("\n--- NOMBRE NORMALIZADO ---\n")
    print(normalize_text(file_name))

    tipo = detect_tipo_documental(text, file_name)
    fields = extract_basic_fields(text, file_name)

    print("\n--- TIPO DETECTADO ---\n")
    print(tipo)

    print("\n--- CAMPOS EXTRAIDOS ---\n")
    for k, v in fields.items():
        print(f"{k}: {v}")

    qr_candidates = extract_qr_candidates(text)

    print("\n--- CANDIDATOS QR ---\n")
    if not qr_candidates:
        print("No se encontraron candidatos QR en el texto.")
    else:
        for i, candidate in enumerate(qr_candidates, start=1):
            print(f"[QR {i}] {candidate[:500]}")
            parsed = parse_qr_payload(candidate)
            print("  -> parseado:")
            pprint.pprint(parsed, width=120)

    fecha_raw = fields.get("fecha_emision")
    fecha_norm = normalize_date(fecha_raw)
    fecha_date = parse_iso_date(fecha_norm) if fecha_norm else None

    print("\n--- FECHA ---\n")
    print("fecha_raw :", fecha_raw)
    print("fecha_norm:", fecha_norm)
    print("fecha_date:", fecha_date)

    print("\n--- REGLA DE NEGOCIO (SIMULACION) ---\n")
    tipo_documental = fields.get("tipo_documental")
    serie = fields.get("serie")
    numero = fields.get("numero")
    ruc = fields.get("ruc")

    es_factura_valida = (
        tipo_documental == "factura"
        and bool(serie)
        and bool(numero)
        and bool(ruc)
        and bool(fecha_date)
    )

    if es_factura_valida:
        year = f"{fecha_date.year}"
        month = f"{fecha_date.month:02d}"
        print("[RESULTADO] FACTURA VALIDA")
        print(f"Se deberia mover a: pendientes_clasificados/{year}/{month}/")
    else:
        print("[RESULTADO] NO ES FACTURA VALIDA COMPLETA")
        print("Se deberia mover a: pendientes_revision/YYYY/MM/")

    print("\n--- RESUMEN MINIMO ---\n")
    resumen = {
        "tipo_documental": tipo_documental,
        "serie": serie,
        "numero": numero,
        "ruc": ruc,
        "fecha_emision": fecha_raw,
        "fecha_norm": fecha_norm,
        "es_factura_valida": es_factura_valida,
    }
    pprint.pprint(resumen, width=120)


if __name__ == "__main__":
    main()