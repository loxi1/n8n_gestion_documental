from pathlib import Path
import cv2
import numpy as np
from pdf2image import convert_from_path

pdf_path = Path(
    r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\files\pendientes_revision\2026\04\f.pdf"
)

out_dir = Path(r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\debug_qr")
out_dir.mkdir(parents=True, exist_ok=True)

pages = convert_from_path(str(pdf_path), dpi=350, first_page=1, last_page=1)

page = pages[0]
img_rgb = np.array(page)
img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

full_path = out_dir / "page1_full.png"
cv2.imwrite(str(full_path), img_bgr)

h, w = img_bgr.shape[:2]

# recorte inferior izquierdo, donde suele estar el QR
crop = img_bgr[int(h * 0.60):h, 0:int(w * 0.35)]
crop_path = out_dir / "page1_qr_crop.png"
cv2.imwrite(str(crop_path), crop)

print("Imagen completa:", full_path)
print("Recorte QR:", crop_path)
print("Dimensiones página:", w, "x", h)
print("Dimensiones recorte:", crop.shape[1], "x", crop.shape[0])