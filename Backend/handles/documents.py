"""Read an uploaded prescription or lab document into text or page images."""

from __future__ import annotations

from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
}


def detect_media(filename: str | None, content_type: str | None) -> str | None:
    raw = (content_type or "").split(";", 1)[0].strip().lower()
    media = _ALIASES.get(raw, raw)
    if media in set(_EXTENSIONS.values()):
        return media
    return _EXTENSIONS.get(Path(filename or "").suffix.lower())


def _pdf_module():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError:
            return None


def pdf_embedded_text(data: bytes) -> str:
    fitz = _pdf_module()
    if fitz is None:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ""
    try:
        return "\n\n".join((page.get_text("text") or "") for page in doc).strip()
    except Exception:
        return ""
    finally:
        doc.close()


def pdf_page_pngs(data: bytes, limit: int = 3) -> list[bytes]:
    fitz = _pdf_module()
    if fitz is None:
        return []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return []
    pages: list[bytes] = []
    try:
        for page in list(doc)[:limit]:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            pages.append(pixmap.tobytes("png"))
    except Exception:
        return pages
    finally:
        doc.close()
    return pages
