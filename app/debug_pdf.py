from pathlib import Path

from core.extractor_pdf import extract_text_from_pdf
from core.classifier import detect_tipo_documental, extract_basic_fields
from core.text_utils import normalize_text
from procesar_pendientes import normalize_date, parse_iso_date

pdf_path = Path(
    r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\files\pendientes_revision\2026\04\posible_documento_20260421233118813_DB9PR05MB10250CA7096BC22409239E8A5BA2C2__1.pdf"
)

file_name = pdf_path.name

print("=" * 80)
print("ARCHIVO:", file_name)
print("=" * 80)

text = extract_text_from_pdf(pdf_path)

print("\n--- PRIMEROS 2500 CARACTERES DEL TEXTO ---\n")
print(text[:2500])

print("\n--- NOMBRE NORMALIZADO ---\n")
print(normalize_text(file_name))

tipo = detect_tipo_documental(text, file_name)
fields = extract_basic_fields(text, file_name)

print("\n--- TIPO DETECTADO ---\n")
print(tipo)

print("\n--- CAMPOS EXTRAIDOS ---\n")
for k, v in fields.items():
    print(f"{k}: {v}")

fecha_norm = normalize_date(fields.get("fecha_emision"))
fecha_date = parse_iso_date(fecha_norm) if fecha_norm else None

print("\n--- FECHA NORMALIZADA ---\n")
print("fecha_norm:", fecha_norm)
print("fecha_date:", fecha_date)