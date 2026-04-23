from pathlib import Path
from core.qr_reader import decode_qr_from_image_path

img_path = Path(
    r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\debug_qr\page1_qr_crop.png"
)

results = decode_qr_from_image_path(img_path)

print("Resultados:")
if not results:
    print("No se pudo leer el QR del recorte.")
else:
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r}")