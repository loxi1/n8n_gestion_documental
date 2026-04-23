from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pdf2image import convert_from_path


def _decode_qr_from_ndarray(img: np.ndarray) -> list[str]:
    detector = cv2.QRCodeDetector()

    results: list[str] = []

    # 1) detección simple
    data, points, _ = detector.detectAndDecode(img)
    if data:
        results.append(data.strip())

    # 2) detección múltiple
    try:
        ok, decoded_info, points_multi, _ = detector.detectAndDecodeMulti(img)
        if ok and decoded_info:
            for item in decoded_info:
                if item and item.strip() and item.strip() not in results:
                    results.append(item.strip())
    except Exception:
        pass

    return results


def _prepare_variants(img_bgr: np.ndarray) -> list[np.ndarray]:
    variants: list[np.ndarray] = []

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    variants.append(gray)

    # binaria
    _, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(th1)

    # invertida
    variants.append(255 - th1)

    # ampliada x2
    up2 = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(up2)

    _, up2_th = cv2.threshold(up2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(up2_th)

    # ampliada x3
    up3 = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    variants.append(up3)

    _, up3_th = cv2.threshold(up3, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(up3_th)

    return variants


def decode_qr_from_image_path(image_path: str | Path) -> list[str]:
    path = Path(image_path)
    if not path.exists():
        return []

    img_bgr = cv2.imread(str(path))
    if img_bgr is None:
        return []

    results: list[str] = []
    for variant in _prepare_variants(img_bgr):
        decoded = _decode_qr_from_ndarray(variant)
        for item in decoded:
            if item not in results:
                results.append(item)

    return results


def decode_qr_from_pdf(
    pdf_path: str | Path,
    poppler_path: str | None = None,
    max_pages: int = 2,
    dpi: int = 250,
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

        for variant in _prepare_variants(img_bgr):
            decoded = _decode_qr_from_ndarray(variant)
            for item in decoded:
                if item not in results:
                    results.append(item)

    return results