from __future__ import annotations

import re
import unicodedata


def strip_accents(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFD", str(value))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def collapse_spaces(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_text(value: str | None) -> str:
    text = strip_accents(value)
    text = text.upper()
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\bN[°º]\b", "NRO", text)
    text = re.sub(r"\bNRO\.\b", "NRO", text)
    text = re.sub(r"\bNO\.\b", "NRO", text)
    text = collapse_spaces(text)
    return text


def normalize_filename_part(value: str | None, fallback: str = "SIN_DATO") -> str:
    if not value:
        return fallback

    text = strip_accents(value)
    text = text.upper()
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    text = collapse_spaces(text)
    text = text.replace(" ", "_")
    text = text.strip("_-")
    return text or fallback