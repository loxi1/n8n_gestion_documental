from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pdf2image import convert_from_path


def _decode_qr_from_ndarray(img: np.ndarray) -> list[str]:
    detector = cv2.QRCodeDetector()
    results: list[str] = []

    data, _, _ = detector.detectAndDecode(img)
    if data:
        results.append(data.strip())

    try:
        ok, decoded_info, _, _ = detector.detectAndDecodeMulti(img)
        if ok and decoded_info:
            for item in decoded_info:
                if item and item.strip() and item.strip() not in results:
                    results.append(item.strip())
    except Exception:
        pass

    return results


def _prepare_variants(img_bgr: np.ndarray) -> list[np.ndarray]:
    variants: list[np.ndarray] = []

    if len(img_bgr.shape) == 2:
        gray = img_bgr
    else:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    variants.append(gray)

    _, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(th1)
    variants.append(255 - th1)

    for scale in (2, ):
        up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        variants.append(up)

        _, up_th = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(up_th)
        variants.append(255 - up_th)

    return variants


def _iter_qr_zones(img_bgr: np.ndarray) -> list[np.ndarray]:
    h, w = img_bgr.shape[:2]

    coords = [
        (0, 0, w, h),                                             # full
        (0, 0, int(w * 0.40), int(h * 0.40)),                     # top_left
        (int(w * 0.60), 0, w, int(h * 0.40)),                     # top_right
        (0, int(h * 0.55), int(w * 0.45), h),                     # bottom_left
        (int(w * 0.55), int(h * 0.55), w, h),                     # bottom_right
        (int(w * 0.55), 0, w, h),                                 # right_full
        (0, 0, int(w * 0.45), h),                                 # left_full
        (0, int(h * 0.55), w, h),                                 # bottom_full
        (int(w * 0.25), int(h * 0.25), int(w * 0.75), int(h * 0.75)), # center
    ]

    zones: list[np.ndarray] = []
    for x1, y1, x2, y2 in coords:
        crop = img_bgr[y1:y2, x1:x2]
        if crop.size > 0:
            zones.append(crop)

    return zones


def decode_qr_from_image_path(image_path: str | Path) -> list[str]:
    path = Path(image_path)
    if not path.exists():
        return []

    img_bgr = cv2.imread(str(path))
    if img_bgr is None:
        return []

    results: list[str] = []

    for zone in _iter_qr_zones(img_bgr):
        for variant in _prepare_variants(zone):
            for item in _decode_qr_from_ndarray(variant):
                if item not in results:
                    results.append(item)

    return results


def decode_qr_from_pdf(
    pdf_path: str | Path,
    poppler_path: str | None = None,
    max_pages: int = 1,
    dpi: int = 280,
) -> list[str]:
    path = Path(pdf_path)
    if not path.exists():
        return []

    results: list[str] = []

    try:
        pages = convert_from_path(
            str(path),
            dpi=dpi,
            first_page=1,
            last_page=max_pages,
            poppler_path=poppler_path,
        )
    except Exception:
        return []

    for page in pages:
        img_rgb = np.array(page)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        for zone in _iter_qr_zones(img_bgr):
            for variant in _prepare_variants(zone):
                for item in _decode_qr_from_ndarray(variant):
                    if item not in results:
                        results.append(item)

    return results