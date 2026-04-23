from pathlib import Path
import pprint

from core.qr_reader import decode_qr_from_pdf
from core.qr_parser import parse_qr_payload

pdf_path = Path(
    r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\files\pendientes_revision\2026\04\f.pdf"
)

print("=" * 80)
print("PDF:", pdf_path)
print("=" * 80)

candidates = decode_qr_from_pdf(pdf_path)

print("\n--- QR ENCONTRADOS ---\n")
if not candidates:
    print("No se encontró QR decodificado.")
else:
    for i, candidate in enumerate(candidates, start=1):
        print(f"[QR {i}] {candidate}\n")
        parsed = parse_qr_payload(candidate)
        print("Parseado:")
        pprint.pprint(parsed, width=120)
        print()