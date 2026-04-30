from pathlib import Path
import cv2
import numpy as np
from pdf2image import convert_from_path

pdf_path = Path(
    r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\files\pendientes_clasificados\2026\04\b.pdf"
)

out_dir = Path(r"C:\D\Proyectos\GestionDocumental\n8n-local\storage\debug_qr")
out_dir.mkdir(parents=True, exist_ok=True)

pages = convert_from_path(str(pdf_path), dpi=350, first_page=1, last_page=1)

page = pages[0]
img_rgb = np.array(page)
img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

h, w = img_bgr.shape[:2]

cv2.imwrite(str(out_dir / "page1_full.png"), img_bgr)

zones = {
    "top_left":        (0, 0, int(w * 0.40), int(h * 0.40)),
    "top_right":       (int(w * 0.60), 0, w, int(h * 0.40)),
    "bottom_left":     (0, int(h * 0.55), int(w * 0.45), h),
    "bottom_right":    (int(w * 0.55), int(h * 0.55), w, h),
    "right_full":      (int(w * 0.55), 0, w, h),
    "left_full":       (0, 0, int(w * 0.45), h),
    "bottom_full":     (0, int(h * 0.55), w, h),
    "center":          (int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75)),
}

print("Imagen completa:", out_dir / "page1_full.png")
print("Dimensiones página:", w, "x", h)

for name, (x1, y1, x2, y2) in zones.items():
    crop = img_bgr[y1:y2, x1:x2]
    crop_path = out_dir / f"page1_qr_crop_{name}.png"
    cv2.imwrite(str(crop_path), crop)
    print(f"{name}: {crop_path} | {crop.shape[1]} x {crop.shape[0]}")