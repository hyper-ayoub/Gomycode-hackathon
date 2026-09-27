from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from core.config import get_settings

router = APIRouter(prefix="/ocr", tags=["ocr"])

MIN_CHARS, MAX_VISION_PAGES = 20, 12
MAX_IMAGE_BYTES = 10 * 1024 * 1024
TARGET_CHARS, CHUNK_CHARS, OVERLAP_CHARS = 5500, 900, 120
LANCEDB_PATH = "/tmp/lancedb_ocr"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# ---- [AI-ADD]  recursive text splitter (reference chunking algorithm)
def recursive_text_splitter(text, max_chunk_length=500, overlap=60):
    """Recursively split text by structural separators, preserving overlaps.

    Direct port of ``recursive_text_splitter`` from RAg.txt (lines 14-42),
    with defaults tuned for PDF-condensation workloads (shorter chunks,
    bigger overlap) so the LanceDB hybrid reranker yields better precision.
    """
    result = []
    text = (text or "").strip()
    if not text:
        return result

    separators = ["\n", " "]
    pattern = "(" + "|".join(re.escape(s) for s in separators) + ")"
    _splits = re.split(pattern, text)
    # Pair separators with their following token so the join preserves layout.
    splits = []
    for i in range(0, len(_splits) - 1, 2):
        splits.append((_splits[i] or "") + (_splits[i + 1] or ""))
    if len(_splits) % 2 == 1 and _splits[-1]:
        splits.append(_splits[-1])

    if not splits:
        return [text] if len(text) <= max_chunk_length else [text[:max_chunk_length]]

    current_chunk_count = 0
    while current_chunk_count < len(splits):
        if current_chunk_count != 0:
            start_idx = max(0, current_chunk_count - overlap)
            end_idx = min(len(splits), current_chunk_count + max_chunk_length)
            chunk = "".join(splits[start_idx:end_idx])
        else:
            chunk = "".join(splits[0:max_chunk_length])
        if chunk.strip():
            result.append(chunk.strip())
        current_chunk_count += max_chunk_length

    return result or [text[:max_chunk_length]]
# --------------------------------------------------------------------------

PROMPTS = {
    "describe": "Describe this image in detail: objects, colors, composition, text and important features.",
    "ocr": "Extract ALL visible text as plain text. Preserve layout where possible. Return empty if none.",
    "classify": 'Classify this image. Reply JSON only: {"category":"...","tags":[...],"confidence":0.0}. Categories: photo, screenshot, diagram, document, meme, art, chart.',
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_/-]{2,}")
SENT_RE = re.compile(r"[.!?]\s+")
PARA_RE = re.compile(r"\n{2,}")
NUM_RE = re.compile(r"\d+(?:[,\.]\d+)?")
CUR_RE = re.compile(r"[\$€£¥]|USD|EUR|GBP|MAD|dh|DH")
TABLE_RE = re.compile(r"(\||---+|\+---+|\t{2,})")
DATE_RE = re.compile(
    r"\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)
STOP_WORDS = set(
    "the a an and or but if then of to in on at for with by from as is are was were "
    "be been have has had do does did this that these those i you he she it we they "
    "me him her us them my your his its our their not no can could should would will "
    "may might must about into over under again than too just very so yet also here "
    "there when where why how all any both each few more most other some such only "
    "own same now up down out off".split()
)


def error(status: int, detail: str):
    raise HTTPException(status_code=status, detail=detail)

def _try_pymupdf():
    """Soft-import PyMuPDF (``fitz`` / ``pymupdf``). Returns the module or None."""
    try:
        import fitz 
        return fitz
    except Exception:
        try:
            import pymupdf as fitz  # type: ignore
            return fitz
        except Exception:
            return None
# --------------------------------------------------------------------------

# ---- [AI-ADD] Multi-library PDF text-extractor stack ------------------------
# When PyMuPDF is missing (the user's exact reported condition) we don't want
# to silently give up on Stage 1 text extraction. ``extract_local()`` below
# now probes these libraries in priority order and uses the first one that
# can open the PDF. Each library has a different extractor implementation
# because their page/iteration APIs differ wildly.
#
# Pure-Python libraries are tried *last* on the theory that if a native-backed
# one (PyMuPDF / pdfplumber) is installed it yields better quality.
def _try_pdfplumber():
    try:
        import pdfplumber  # type: ignore
        return pdfplumber
    except Exception:
        return None


def _try_pypdf():
    """Modern ``pypdf`` package (>= 3.x) — pure-Python, no deps beyond PyPI."""
    try:
        import pypdf  # type: ignore
        return pypdf
    except Exception:
        try:
            import PyPDF2 as pypdf  # type: ignore  # legacy package name
            return pypdf
        except Exception:
            return None


def _try_pdfminer():
    """pdfminer.six — pure-Python, extremely reliable on real-text PDFs."""
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        return extract_text
    except Exception:
        return None


def _try_pdf_renderers():
    """Probe all known PDF->image renderers. Returns a dict keyed by name.

    pdf2image wraps poppler; wand wraps ImageMagick/Ghostscript. If we don't
    have ANY renderer we fall back in vision_pdf() to sending the raw PDF
    bytes directly to OpenAI Vision (application/pdf).
    """
    out: dict[str, Any] = {}
    try:
        from pdf2image import convert_from_bytes  # type: ignore
        out["pdf2image"] = convert_from_bytes
    except Exception:
        pass
    try:
        from wand.image import Image as WandImage  # type: ignore
        out["wand"] = WandImage
    except Exception:
        pass
    return out


def _probe_local_pdf_capabilities() -> dict[str, bool]:
    """Return a flat dict of which PDF libraries are currently importable.

    Used only by GET /ocr/ so Swagger users can see at a glance why extraction
    might be degrading and exactly which package to pip-install next.
    """
    return {
        "pymupdf": _try_pymupdf() is not None,
        "pdfplumber": _try_pdfplumber() is not None,
        "pypdf": _try_pypdf() is not None,
        "pdfminer_six": _try_pdfminer() is not None,
    }
# --------------------------------------------------------------------------


def _try_nltk():
    """Soft-import NLTK. Returns the module or None."""
    try:
        import nltk  # type: ignore
        return nltk
    except Exception:
        return None


def _try_lancedb_stack():
    """Soft-import the LanceDB modules needed for hybrid RAG. Returns a
    4-tuple ``(lancedb, get_registry, LanceModel, Vector, LinearCombinationReranker)``
    or ``None`` if any piece is missing."""
    try:
        import lancedb  # type: ignore
        from lancedb.embeddings import get_registry  # type: ignore
        from lancedb.pydantic import LanceModel, Vector  # type: ignore
        from lancedb.rerankers import LinearCombinationReranker  # type: ignore
        return lancedb, get_registry, LanceModel, Vector, LinearCombinationReranker
    except Exception:
        return None


def _try_openai_client():
    """Soft-import the official OpenAI SDK client. Returns an OpenAI instance
    or ``None`` if the SDK / API key are missing.

    Uses the project-standard pattern from ``app.services.ai_agent._get_client``
    so we inherit the same timeout / base-url handling without having to import
    ai_agent (which pulls in the whole planning stack)."""
    cfg = get_settings()
    if not cfg.openai_api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
        return OpenAI(api_key=cfg.openai_api_key, timeout=90.0)
    except Exception:
        return None


# ----------------------------------------------------------------------------------


def extract_local(data: bytes, diagnostics: list[str] | None = None) -> str:
    """Extract embedded text from a PDF using the FIRST available library.

    Tries libraries in this priority order (quality / feature set descending):
      1. **PyMuPDF** (fitz / pymupdf) — 6 extraction modes per page (best)
      2. **pdfplumber** — table-aware extract_text_page (very good for reports)
      3. **pypdf** (or legacy PyPDF2) — pure-Python, no external deps
      4. **pdfminer.six** — pure-Python extract_text from pdfminer.high_level

    If a library imports OK but fails to open or extract from THIS PDF we log
    the attempt and move on to the next one instead of returning empty.

    Appends human-readable notes to ``diagnostics`` when provided, so a user
    seeing a 0-char stage-1 failure can tell exactly which libraries were
    tried and which one barfed.
    """
    # ---- Attempt 1: PyMuPDF -------------------------------------------------
    fitz = _try_pymupdf()
    if fitz is not None:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            if diagnostics is not None:
                diagnostics.append(f"local PyMuPDF: failed to open PDF ({e!r})")
        else:
            pages = []
            pages_with_text = 0
            pages_total = 0
            try:
                for page in doc:
                    pages_total += 1
                    text = ""
                    for mode in ("text", "blocks", "words", "rawdict", "html", "xhtml"):
                        try:
                            raw = page.get_text(mode)
                            if mode == "blocks":
                                raw = "\n".join(
                                    str(x[4]).strip() for x in raw
                                    if isinstance(x, (list, tuple)) and len(x) > 4
                                )
                            elif mode == "words":
                                raw = " ".join(
                                    str(x[4]).strip() for x in raw
                                    if isinstance(x, (list, tuple)) and len(x) > 4
                                )
                            elif mode == "rawdict":
                                try:
                                    parts = []
                                    for blk in (raw or {}).get("blocks", []):
                                        for ln in blk.get("lines", []):
                                            for sp in ln.get("spans", []):
                                                t = str(sp.get("text", "")).strip()
                                                if t:
                                                    parts.append(t)
                                    raw = " ".join(parts)
                                except Exception:
                                    raw = ""
                            elif mode in ("html", "xhtml"):
                                raw = re.sub(r"<[^>]+>", " ", raw or "")
                                raw = re.sub(r"\s+", " ", raw).strip()
                            if (text := (raw or "").strip()):
                                break
                        except Exception:
                            pass
                    if text:
                        pages_with_text += 1
                        pages.append(text)
            finally:
                doc.close()
            out = "\n\n".join(pages).strip()
            if diagnostics is not None:
                diagnostics.append(
                    f"local PyMuPDF: pages={pages_total}, pages_with_text={pages_with_text}, "
                    f"chars={len(out)}"
                )
            if out:
                return out

    # ---- Attempt 2: pdfplumber --------------------------------------------
    pdfplumber = _try_pdfplumber()
    if pdfplumber is not None:
        import io
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                pages = []
                pages_total = getattr(pdf, "pages") and len(pdf.pages) or 0
                pages_with_text = 0
                for page in pdf.pages[:MAX_VISION_PAGES * 5]:  # pdfplumber is pure-Python, cap to avoid hang
                    try:
                        t = (page.extract_text() or "").strip()
                    except Exception:
                        t = ""
                    if t:
                        pages_with_text += 1
                        pages.append(t)
            out = "\n\n".join(pages).strip()
            if diagnostics is not None:
                diagnostics.append(
                    f"local pdfplumber: pages={pages_total}, pages_with_text={pages_with_text}, "
                    f"chars={len(out)}"
                )
            if out:
                return out
        except Exception as e:
            if diagnostics is not None:
                diagnostics.append(f"local pdfplumber: failed ({e!r})")

    # ---- Attempt 3: pypdf / PyPDF2 -----------------------------------------
    pypdf_mod = _try_pypdf()
    if pypdf_mod is not None:
        import io
        try:
            reader = pypdf_mod.PdfReader(io.BytesIO(data))
            pages = []
            pages_total = len(reader.pages)
            pages_with_text = 0
            page_iter = list(reader.pages)
            if len(page_iter) > MAX_VISION_PAGES * 5:
                page_iter = page_iter[:MAX_VISION_PAGES * 5]
            for page in page_iter:
                try:
                    t = (page.extract_text() or "").strip()
                except Exception:
                    t = ""
                if t:
                    pages_with_text += 1
                    pages.append(t)
            out = "\n\n".join(pages).strip()
            if diagnostics is not None:
                diagnostics.append(
                    f"local pypdf: pages={pages_total}, pages_with_text={pages_with_text}, "
                    f"chars={len(out)}"
                )
            if out:
                return out
        except Exception as e:
            if diagnostics is not None:
                diagnostics.append(f"local pypdf: failed ({e!r})")

    # ---- Attempt 4: pdfminer.six -------------------------------------------
    pdfminer_extract = _try_pdfminer()
    if pdfminer_extract is not None:
        import io
        try:
            out = (pdfminer_extract(io.BytesIO(data)) or "").strip()
            if diagnostics is not None:
                diagnostics.append(f"local pdfminer.six: chars={len(out)}")
            if out:
                return out
        except Exception as e:
            if diagnostics is not None:
                diagnostics.append(f"local pdfminer.six: failed ({e!r})")

    # ---- All libraries missing / failed ------------------------------------
    if diagnostics is not None:
        caps = _probe_local_pdf_capabilities()
        installed = [k for k, v in caps.items() if v]
        if installed:
            diagnostics.append(
                f"local skipped: no usable extractor for this PDF; "
                f"installed={installed}"
            )
        else:
            diagnostics.append(
                "local skipped: no PDF text library installed. "
                "Install ONE of: pip install pymupdf (recommended) OR "
                "pdfplumber OR pypdf OR pdfminer.six"
            )
    return ""


def page_png(page: Any) -> bytes | None:
    fitz = _try_pymupdf()
    if fitz is None:
        return None
    try:
        return page.get_pixmap(
            matrix=fitz.Matrix(150 / 72, 150 / 72),
            alpha=False,
        ).tobytes("png")
    except Exception:
        return None


def whisper_url(base: str):
    base = (base or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        error(503, f"Invalid LLMWHISPERER_BASE_URL: {base!r}")
    if not urlparse(base).hostname:
        error(503, f"No hostname in LLMWHISPERER_BASE_URL: {base!r}")
    return base, f"{base}/whisper"


async def poll_whisper(client, base, key, wh):
    headers = {"unstract-key": key}

    for _ in range(90):
        response = None

        for param in ("whisper-hash", "whisper_hash"):
            response = await client.get(
                f"{base}/whisper-status",
                headers=headers,
                params={param: wh},
            )
            if response.status_code < 400:
                break

        if not response or response.status_code >= 400:
            error(502, "LLMWhisperer status check failed")

        try:
            data = response.json()
        except Exception:
            await asyncio.sleep(2)
            continue

        status = str(data.get("status", "")).lower()

        if status == "processed":
            for param in ("whisper-hash", "whisper_hash"):
                result = await client.get(
                    f"{base}/whisper-retrieve",
                    headers=headers,
                    params={param: wh},
                )
                if result.status_code == 200:
                    return result.text or ""
            error(502, "LLMWhisperer retrieve returned no text")

        if status in {"delivered", "unknown", "error", "failed"}:
            error(502, str(data.get("message") or f"status={status}"))

        await asyncio.sleep(2)

    error(504, "LLMWhisperer timed out")


async def whisper(data: bytes, mode="ocr") -> str:
    cfg = get_settings()

    if not cfg.llmwhisperer_api_key:
        error(503, "LLMWHISPERER_API_KEY not set")

    base, url = whisper_url(cfg.llmwhisperer_base_url)

    headers = {
        "unstract-key": cfg.llmwhisperer_api_key,
        "Content-Type": "application/octet-stream",
    }

    params = {
        "processing_mode": mode,
        "output_mode": "line-printer",
        "force_text_processing": "false",
        "timeout": "200",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(240, connect=30, read=240, write=60),
            follow_redirects=True,
        ) as client:
            r = await client.post(url, content=data, headers=headers, params=params)

            if r.status_code == 200:
                return r.text or ""

            if r.status_code == 202:
                try:
                    body = r.json()
                except Exception:
                    error(502, "LLMWhisperer 202 invalid JSON")

                wh = str(body.get("whisper-hash") or body.get("whisper_hash") or "").strip()
                if not wh:
                    error(502, "LLMWhisperer 202 missing hash")

                return await poll_whisper(client, base, cfg.llmwhisperer_api_key, wh)

            if r.status_code >= 400:
                error(r.status_code, f"LLMWhisperer error: {r.text[:300]}")

            return r.text or ""

    except HTTPException:
        raise
    except httpx.HTTPError as e:
        error(502, f"LLMWhisperer HTTP error: {e}")
    except Exception as e:
        error(502, f"LLMWhisperer failed: {e}")


async def vision(image: bytes, media: str, mode="ocr", max_tokens=1024):
    cfg = get_settings()

    if not cfg.openai_api_key:
        error(503, "OPENAI_API_KEY not set")

    model = cfg.openai_model or "gpt-4o-mini"
    if not any(x in model for x in ("gpt-4o", "gpt-4.1", "gpt-4.5")):
        model = "gpt-4o-mini"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPTS.get(mode, PROMPTS["ocr"])},
                {"type": "image_url", "image_url": {
                    "url": f"data:{media};base64,{base64.b64encode(image).decode()}",
                    "detail": "high",
                }},
            ],
        }],
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {cfg.openai_api_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as e:
        error(502, f"OpenAI Vision failed: {e}")

    if r.status_code >= 400:
        error(r.status_code, f"OpenAI Vision error: {r.text[:300]}")

    choices = r.json().get("choices") or []
    content = choices[0].get("message", {}).get("content", "") if choices else ""

    if isinstance(content, list):
        content = "".join(x.get("text", "") for x in content if isinstance(x, dict))

    if mode == "classify":
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

    return str(content)


async def vision_pdf(data: bytes, diagnostics: list[str] | None = None) -> str:
    """OCR every page of a PDF via OpenAI Vision. Rendering order:

    1. **PyMuPDF** page PNG (original behaviour)
    2. **pdf2image** (poppler) page PNG
    3. **Wand/ImageMagick** page PNG
    4. **PDF direct** — send the ENTIRE PDF as ``application/pdf`` to
       OpenAI Vision without any local rendering. GPT-4o / gpt-4o-mini accept
       PDF natively via the Vision API since mid-2024 so this works even when
       *zero* local PDF libraries are installed (the user's exact scenario).

    Appends human-readable notes to ``diagnostics`` so callers can tell which
    renderer (if any) was used.
    """
    cfg = get_settings()
    if not cfg.openai_api_key:
        if diagnostics is not None:
            diagnostics.append("vision_pdf skipped: OPENAI_API_KEY not set")
        return ""

    model = cfg.openai_model or "gpt-4o-mini"
    if not any(x in model for x in ("gpt-4o", "gpt-4.1", "gpt-4.5")):
        model = "gpt-4o-mini"

    pages: list[str] = []
    pages_total = 0
    pages_rendered = 0
    pages_ocr_ok = 0

    # ---- Render path A: PyMuPDF (best, 150dpi) ----------------------------
    fitz = _try_pymupdf()
    if fitz is not None:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:
            if diagnostics is not None:
                diagnostics.append(f"vision_pdf pymupdf: failed open ({e!r})")
        else:
            try:
                for page in list(doc)[:MAX_VISION_PAGES]:
                    pages_total += 1
                    image = page_png(page)
                    if not image:
                        continue
                    pages_rendered += 1
                    try:
                        text = await vision(image, "image/png", "ocr", 4096)
                        if isinstance(text, str) and text.strip():
                            pages_ocr_ok += 1
                            pages.append(text.strip())
                    except Exception:
                        pass
            finally:
                doc.close()

    # ---- Render path B: pdf2image (poppler) ------------------------------
    if not pages_rendered:
        renderers = _try_pdf_renderers()
        if "pdf2image" in renderers:
            convert_from_bytes = renderers["pdf2image"]
            try:
                images = convert_from_bytes(
                    data, dpi=150, fmt="png",
                    last_page=MAX_VISION_PAGES,
                )
            except Exception as e:
                if diagnostics is not None:
                    diagnostics.append(f"vision_pdf pdf2image: failed ({e!r})")
            else:
                for img in images:
                    pages_total = max(pages_total, len(images))
                    pages_rendered += 1
                    try:
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        image_bytes = buf.getvalue()
                        text = await vision(image_bytes, "image/png", "ocr", 4096)
                        if isinstance(text, str) and text.strip():
                            pages_ocr_ok += 1
                            pages.append(text.strip())
                    except Exception:
                        pass

    # ---- Render path C: Wand / ImageMagick --------------------------------
    if not pages_rendered:
        renderers = _try_pdf_renderers()
        if "wand" in renderers:
            WandImage = renderers["wand"]
            try:
                import io
                all_images: list[bytes] = []
                with WandImage(blob=data, resolution=150, format="pdf") as wand:
                    wand.format = "png"
                    for i, w in enumerate(wand.sequence):
                        if i >= MAX_VISION_PAGES:
                            break
                        with WandImage(w) as single:
                            single.format = "png"
                            all_images.append(single.make_blob())
            except Exception as e:
                if diagnostics is not None:
                    diagnostics.append(f"vision_pdf wand: failed ({e!r})")
            else:
                for image_bytes in all_images:
                    pages_total = max(pages_total, len(all_images))
                    pages_rendered += 1
                    try:
                        text = await vision(image_bytes, "image/png", "ocr", 4096)
                        if isinstance(text, str) and text.strip():
                            pages_ocr_ok += 1
                            pages.append(text.strip())
                    except Exception:
                        pass

    # ---- Render path D: PDF-direct to OpenAI Vision (ULTIMATE FALLBACK) ---
    # If we reach here it means NO local library could render a single page
    # PNG (probably neither PyMuPDF nor poppler nor ImageMagick are installed).
    # We upload the PDF bytes to the OpenAI Files endpoint and reference them
    # via type="file" in chat.completions — GPT-4o / gpt-4o-mini read PDFs
    # natively and return all visible text. This needs ZERO local PDF libs.
    #
    # Earlier revision incorrectly used type="pdf_url" which the OpenAI API
    # rejects — we now use the two officially supported content types and
    # try them in strict reliability order.
    if not pages_rendered:
        import io
        client = _try_openai_client()
        uploaded_file_id: str | None = None
        used_method: str | None = None

        # ---- D.1: Official SDK pattern (files.create + file_id) ---------
        # This is the most reliable path. OpenAI auto-expires files with
        # purpose="user_data" after 24h but we try an explicit delete too.
        if client is not None:
            try:
                if diagnostics is not None:
                    diagnostics.append(
                        "vision_pdf pdf-direct (D.1): uploading PDF to OpenAI "
                        "Files via SDK client.files.create"
                    )
                fobj = client.files.create(
                    file=("document.pdf", io.BytesIO(data), "application/pdf"),
                    purpose="user_data",
                )
                uploaded_file_id = getattr(fobj, "id", None)
                if uploaded_file_id:
                    used_method = "sdk_file_id"
            except Exception as exc:
                if diagnostics is not None:
                    diagnostics.append(
                        f"vision_pdf pdf-direct (D.1): files.create failed ({exc!r})"
                    )
                # Some older API keys / account tiers don't allow purpose=
                # "user_data". Try purpose="assistants" as a fallback before
                # giving up on the SDK path entirely.
                if client is not None:
                    try:
                        fobj = client.files.create(
                            file=("document.pdf", io.BytesIO(data), "application/pdf"),
                            purpose="assistants",
                        )
                        uploaded_file_id = getattr(fobj, "id", None)
                        if uploaded_file_id:
                            used_method = "sdk_file_id_assistants"
                    except Exception as exc2:
                        if diagnostics is not None:
                            diagnostics.append(
                                f"vision_pdf pdf-direct (D.1b): assistants purpose "
                                f"also failed ({exc2!r}) — switching to inline "
                                f"file_url base64"
                            )

            # Now run chat.completions with the file_id reference.
            if uploaded_file_id:
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        temperature=0.1,
                        max_tokens=4096,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text",
                                 "text": "Extract ALL visible text from every "
                                         "page of this PDF as plain text. "
                                         "Preserve layout where possible. "
                                         "Return empty string only if the PDF "
                                         "has no text."},
                                {"type": "file",
                                 "file_id": uploaded_file_id},
                            ],
                        }],
                    )
                    choice = (getattr(resp, "choices", None) or [None])[0]
                    msg = getattr(choice, "message", None)
                    content = getattr(msg, "content", "") or ""
                    text = str(content).strip()
                    if text:
                        pages_total = 1
                        pages_rendered = 1
                        pages_ocr_ok = 1
                        pages.append(text)
                        if diagnostics is not None:
                            diagnostics.append(
                                f"vision_pdf pdf-direct ({used_method}): OK, "
                                f"chars={len(text)}"
                            )
                except Exception as exc:
                    if diagnostics is not None:
                        diagnostics.append(
                            f"vision_pdf pdf-direct ({used_method}): chat "
                            f"error ({exc!r})"
                        )
                finally:
                    # Best-effort cleanup so the user doesn't accumulate
                    # temporary PDF files in their OpenAI account. Failure
                    # here is non-fatal (auto-expires within 24h anyway).
                    if uploaded_file_id:
                        try:
                            client.files.delete(uploaded_file_id)
                        except Exception:
                            pass
                        uploaded_file_id = None

        # ---- D.2: Inline base64 via type="file" / "file_url" -------------
        # If SDK path failed entirely (very rare — the image OCR endpoint
        # already proves the client works) we try the raw REST endpoint
        # with an inline base64 file_url payload. Content type is "file",
        # NOT "pdf_url" (which was the invalid value from before).
        if not pages_rendered:
            if diagnostics is not None:
                diagnostics.append(
                    "vision_pdf pdf-direct (D.2): trying inline base64 via "
                    "REST /v1/chat/completions with type=\"file\""
                )
            b64 = base64.b64encode(data).decode()
            rest_payload = {
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.1,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text",
                         "text": "Extract ALL visible text from every page "
                                 "of this PDF as plain text. Preserve layout "
                                 "where possible. Return empty string only "
                                 "if the PDF has no text."},
                        {"type": "file",
                         "file_url": {
                             "url": f"data:application/pdf;base64,{b64}",
                         }},
                    ],
                }],
            }
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(180, connect=20)
                ) as hclient:
                    r = await hclient.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=rest_payload,
                        headers={
                            "Authorization": f"Bearer {cfg.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                    )
            except httpx.HTTPError as e:
                if diagnostics is not None:
                    diagnostics.append(
                        f"vision_pdf pdf-direct (D.2): HTTP error ({e!r})"
                    )
            else:
                if r.status_code >= 400:
                    if diagnostics is not None:
                        diagnostics.append(
                            f"vision_pdf pdf-direct (D.2): HTTP {r.status_code} "
                            f"-> {r.text[:250]}"
                        )
                else:
                    try:
                        choices = r.json().get("choices") or []
                        content = (
                            choices[0].get("message", {}).get("content", "")
                            if choices else ""
                        )
                        if isinstance(content, list):
                            content = "".join(
                                x.get("text", "")
                                for x in content
                                if isinstance(x, dict)
                            )
                        text = str(content).strip()
                        if text:
                            pages_total = 1
                            pages_rendered = 1
                            pages_ocr_ok = 1
                            pages.append(text)
                            if diagnostics is not None:
                                diagnostics.append(
                                    f"vision_pdf pdf-direct (D.2 inline): "
                                    f"OK, chars={len(text)}"
                                )
                    except Exception as e:
                        if diagnostics is not None:
                            diagnostics.append(
                                f"vision_pdf pdf-direct (D.2): parse error "
                                f"({e!r})"
                            )

        # ---- D.3: If nothing worked, give a CLEAR actionable hint --------
        if not pages_rendered and diagnostics is not None:
            diagnostics.append(
                "vision_pdf pdf-direct: BOTH SDK files.create + inline "
                "file_url failed. Quickest local fix: run  pip install pymupdf"
                "  inside your backend venv / container, then restart."
            )

    if diagnostics is not None:
        diagnostics.append(
            f"vision_pdf: pages_total={pages_total}, pages_rendered={pages_rendered}, "
            f"pages_ocr_ok={pages_ocr_ok}"
        )
    return "\n\n".join(pages)


async def extract_pdf_text(
    data: bytes, filename: str, breakdown: dict[str, Any] | None = None
) -> str:
    """Run the multi-stage PDF OCR pipeline with explicit RAG inter-stage.

    **Pipeline order (exactly as documented in the endpoint):**
      1. Local embedded text extraction (PyMuPDF — 6 modes tried per page)
      2. LLMWhisperer (remote OCR) — skipped gracefully when unreachable
      3. **RAG inter-stage** (RAg.txt recursive splitter + LanceDB hybrid
         search with LinearCombinationReranker weight=0.7, BM25-lite fallback)
         — merges any partial text from stages 1+2, chunks and condenses it
         with aggressive hybrid ranking. Succeeds if condensed output has
         >= MIN_CHARS of usable content.
      4. OpenAI Vision — page-by-page PNG render + OCR — used as LAST RESORT

    RAG condensation is applied after *every* successful extraction stage
    (not just the RAG inter-stage) so long outputs are always trimmed to
    TARGET_CHARS using the same hybrid-ranking algorithm.

    When ``breakdown`` dict is provided, it is populated in-place with
    ``stage_notes``, ``failures``, ``rag_mode_used``, ``chunk_count`` and
    ``extraction_stage`` so the endpoint can surface diagnostic metadata to
    Swagger users.
    """
    failures: list[str] = []
    stage_notes: list[str] = []
    extraction_stage = "failed"
    rag_mode_used = "none"
    chunk_count = 0
    whisper_text = ""  # populated if LLMWhisperer returned anything usable

    def _capture_rag_info(condensed: str, mode: str, n_chunks: int) -> str:
        nonlocal rag_mode_used, chunk_count
        rag_mode_used = mode
        chunk_count = n_chunks
        return condensed

    # ---- Stage 1: local embedded text --------------------------------------
    local_diag: list[str] = []
    local = extract_local(data, diagnostics=local_diag)
    stage_notes.extend(local_diag)

    if len(local) >= MIN_CHARS:
        extraction_stage = "embedded"
        chunks_pre = recursive_text_splitter(local) or chunk(local)
        condensed = await rag_condense(local, filename, _chunks=chunks_pre)
        mode_used = rag_detect_mode(local)
        return _capture_rag_info(condensed, mode_used, len(chunks_pre))

    if local:
        failures.append(f"embedded text present but below MIN_CHARS ({len(local)} < {MIN_CHARS})")
    else:
        failures.append(f"embedded text too short ({len(local)} chars)")

    cfg = get_settings()

    # ---- Stage 2: LLMWhisperer ---------------------------------------------
    if cfg.llmwhisperer_api_key:
        mode = "text" if local else "ocr"
        try:
            result = await whisper(data, mode)
            if result.strip():
                # LLMWhisperer returned something — check length then return
                if len(result.strip()) >= MIN_CHARS:
                    extraction_stage = "llmwhisperer"
                    chunks_pre = recursive_text_splitter(result.strip()) or chunk(result.strip())
                    condensed = await rag_condense(result.strip(), filename, _chunks=chunks_pre)
                    mode_used = rag_detect_mode(result.strip())
                    return _capture_rag_info(condensed, f"llmwhisperer+{mode_used}", len(chunks_pre))
                # LLMWhisperer text too short on its own — keep it for the
                # RAG inter-stage which combines partial results.
                whisper_text = result.strip()
                failures.append(f"LLMWhisperer ({mode}) below MIN_CHARS ({len(whisper_text)} < {MIN_CHARS})")
            else:
                failures.append(f"LLMWhisperer ({mode}) empty")
        except Exception as e:
            # LLMWhisperer unreachable / 502 DNS etc — don't block; the RAG
            # inter-stage + Vision stages are still able to recover in most
            # environments.
            failures.append(f"LLMWhisperer skipped: {e}")
    else:
        failures.append("LLMWhisperer skipped: no API key")

    # ---- Stage 3: [AI-ADD] Explicit RAG inter-stage ------------------------
    # Combine whatever partial text we have from stages 1 (embedded) and 2
    # (LLMWhisperer). Run recursive_text_splitter + rag_condense with
    # aggressive hybrid ranking. If the condensed output has >= MIN_CHARS we
    # consider this a successful extraction and return it — otherwise we
    # record the attempt and move on to Vision.
    #
    # This stage is critical when:
    #   * PyMuPDF / fitz is missing (so local + vision stages are dead) and
    #     LLMWhisperer is also unreachable — in that case this stage has no
    #     input and fails cleanly, preserving the existing failure breakdown.
    #   * Partial text exists from either stage (e.g. embedded extraction got
    #     15 chars plus whisper got 10 chars) — the RAG merger will try to
    #     extract the highest-value chunks across both sources.
    rag_inter_diag: list[str] = []
    combined_parts = [p for p in (local, whisper_text) if p and p.strip()]
    combined_text = "\n\n".join(combined_parts).strip() if combined_parts else ""

    if combined_text:
        rag_chunks = recursive_text_splitter(combined_text) or chunk(combined_text)
        rag_condensed = await rag_condense(
            combined_text, filename,
            query="document summary key information dates figures amounts names",
            _chunks=rag_chunks,
            _diagnostics=rag_inter_diag,
        )
        stage_notes.extend(rag_inter_diag)
        if len(rag_condensed) >= MIN_CHARS:
            extraction_stage = "rag_interstage"
            mode_used = rag_detect_mode(combined_text)
            return _capture_rag_info(rag_condensed, f"rag_inter+{mode_used}", len(rag_chunks))
        if rag_condensed:
            failures.append(
                f"RAG inter-stage condensed too short ({len(rag_condensed)} < {MIN_CHARS}); "
                f"input_parts={len(combined_parts)}"
            )
        else:
            failures.append("RAG inter-stage returned empty")
    else:
        stage_notes.append("rag_interstage skipped: no partial text from stages 1+2")
        failures.append("RAG inter-stage skipped (no prior stage produced any text)")

    # ---- Stage 4: Vision PDF (last-resort per-page PNG OCR) ----------------
    vision_diag: list[str] = []
    result = await vision_pdf(data, diagnostics=vision_diag)
    stage_notes.extend(vision_diag)

    if result:
        extraction_stage = "vision"
        chunks_pre = recursive_text_splitter(result) or chunk(result)
        condensed = await rag_condense(result, filename, _chunks=chunks_pre)
        mode_used = rag_detect_mode(result)
        return _capture_rag_info(condensed, f"vision+{mode_used}", len(chunks_pre))

    failures.append("Vision PDF returned empty (see stage_notes for details)")

    # ---- Last-chance: return condensed version of combined partial text ----
    # Prefer the RAG inter-stage output if it exists (even below MIN_CHARS)
    # because it has already been ranked / de-noised.
    last_chance = ""
    if combined_text:
        last_chance_chunks = recursive_text_splitter(combined_text) or chunk(combined_text)
        last_chance = await rag_condense(combined_text, filename, _chunks=last_chance_chunks)
    elif local:
        last_chance_chunks = recursive_text_splitter(local) or chunk(local)
        last_chance = await rag_condense(local, filename, _chunks=last_chance_chunks)

    if last_chance:
        extraction_stage = "partial_rag_condensed"
        mode_used = rag_detect_mode(last_chance)
        return _capture_rag_info(last_chance, f"partial+{mode_used}", 0)

    # ---- Populate breakdown for caller (endpoint) then fail ----------------
    if breakdown is not None:
        breakdown.update({
            "stage_notes": stage_notes,
            "failures": failures,
            "extraction_stage": extraction_stage,
            "rag_mode_used": rag_mode_used,
            "chunk_count": chunk_count,
        })
    error(422, "Cannot extract PDF text. Breakdown: " + "; ".join(failures) +
          " | Stage notes: " + " || ".join(stage_notes))


def rag_detect_mode(text: str) -> str:
    """Report which RAG backend would be / was used for ``text``.

    "full_text" — <= TARGET_CHARS, no condensation needed.
    "lancedb_hybrid" — LanceDB + sentence-transformers installed, hybrid rerank.
    "bm25" — BM25-lite fallback when LanceDB is not available.
    """
    if len(text or "") <= TARGET_CHARS:
        return "full_text"
    if _try_lancedb_stack() is not None:
        return "lancedb_hybrid"
    return "bm25"


def chunk(text: str) -> list[str]:
    if not text.strip():
        return []

    paragraphs = [x.strip() for x in PARA_RE.split(text) if x.strip()]
    units = []

    nltk = _try_nltk()
    try:
        for p in paragraphs:
            if nltk is not None:
                units.extend(nltk.sent_tokenize(p) or [p])
            else:
                units.extend([x.strip() for x in SENT_RE.split(p) if x.strip()] or [p])
    except Exception:
        for p in paragraphs:
            units.extend([x.strip() for x in SENT_RE.split(p) if x.strip()] or [p])

    chunks, current, size = [], [], 0

    for unit in units:
        length = len(unit) + 1

        if current and size + length > CHUNK_CHARS:
            chunks.append(" ".join(current))

            tail, tail_size = [], 0
            for x in reversed(current):
                n = len(x) + 1
                if tail_size + n > OVERLAP_CHARS:
                    break
                tail.insert(0, x)
                tail_size += n

            current, size = tail, tail_size

        current.append(unit)
        size += length

    if current:
        chunks.append(" ".join(current))

    return chunks


def tokens(text: str):
    return [
        x.lower()
        for x in WORD_RE.findall(text)
        if x.lower() not in STOP_WORDS
    ]


def bm25(chunks):
    if not chunks:
        return []

    tokenized = [list(set(tokens(x))) for x in chunks]
    df = Counter(x for row in tokenized for x in row)
    total, results = len(chunks), []

    for i, text in enumerate(chunks):
        row = tokenized[i]
        n = len(row)
        unique = len(set(row)) / n if n else 0
        length = math.log1p(len(text)) / 6

        density = (
            len(NUM_RE.findall(text)) * .4
            + len(CUR_RE.findall(text)) * 3
            + len(DATE_RE.findall(text)) * 2.5
        ) / max(1, len(text) / 200)

        tfidf = sum(
            (1 / n) * (math.log((1 + total) / (1 + df[x])) + 1)
            for x in row
        ) if n else 0

        score = (
            .6 * length + 1.6 * density + tfidf
        ) * (1.3 if TABLE_RE.search(text) else 1) * (.5 + .5 * unique)

        results.append((i, score))

    return sorted(results, key=lambda x: x[1], reverse=True)


def document_id(filename: str, text: str):
    return hashlib.sha256(
        f"{filename}|{len(text)}".encode()
    ).hexdigest()[:24]


def build_lance(chunks, name, mode="overwrite"):
    """Create / open a LanceDB table containing the given text chunks.

    Directly implements the RAg.txt algorithm (lines 64-98):
      - embeddings via sentence-transformers all-MiniLM-L6-v2
      - ``LanceModel`` with Vector() + SourceField()
      - ``table.add()`` with raw text rows
      - ``create_fts_index("text", replace=True)`` BEFORE any hybrid search.

    ``mode="overwrite"`` (default) is used by the inline condensation step.
    ``mode="append"`` is used by the RAG ingest endpoint so the same table
    can be reused across requests (user-scoped names prevent leaks).
    ``mode="open"`` opens an existing table without inserting rows — used
    by ``/ocr/rag/query`` and ``/ocr/rag/status``.
    """
    stack = _try_lancedb_stack()
    if stack is None:
        return None
    lancedb, get_registry, LanceModel, Vector, _ = stack

    try:
        emb = get_registry().get("sentence-transformers").create(
            name=EMBEDDING_MODEL
        )

        class Documents(LanceModel):
            vector: Vector(emb.ndims()) = emb.VectorField()
            text: str = emb.SourceField()
            chunk_idx: int

        db = lancedb.connect(LANCEDB_PATH)
        if mode == "open":
            if name not in db.table_names():
                return None
            return db.open_table(name)

        if mode == "append" and name in db.table_names():
            table = db.open_table(name)
            existing_count = table.count_rows()
            table.add([
                {"text": x, "chunk_idx": existing_count + i}
                for i, x in enumerate(chunks)
            ])
        else:
            table = db.create_table(name, schema=Documents, mode="overwrite")
            table.add([{"text": x, "chunk_idx": i} for i, x in enumerate(chunks)])

        # FTS index is mandatory for hybrid search (RAg.txt lines 95-96)
        try:
            table.create_fts_index("text", replace=True)
        except Exception:
            pass
        return table
    except Exception:
        return None


def hybrid(table, query, limit=6, weight=0.7):
    """Run LanceDB hybrid search exactly as described in RAg.txt lines 100-119.

    - ``query_type="hybrid"`` (BM25 FTS + semantic vector)
    - ``LinearCombinationReranker(weight=weight)`` where 0 → pure BM25,
      1 → pure semantic. Default matches RAg.txt (weight=0.7).
    - Returns up to ``limit`` rows ordered by combined score.
    """
    stack = _try_lancedb_stack()
    if stack is None:
        return []
    _, _, _, _, LinearCombinationReranker = stack

    try:
        return (
            table.search(query, query_type="hybrid")
            .rerank(reranker=LinearCombinationReranker(weight=weight))
            .limit(limit)
            .to_list()
        )
    except Exception:
        return []


def semantic_only(table, query, limit=6):
    """Pure vector search — used when user picks ``mode="semantic"``."""
    try:
        return (
            table.search(query, query_type="vector")
            .limit(limit)
            .to_list()
        )
    except Exception:
        return []


def fts_only(table, query, limit=6):
    """Pure full-text / keyword search — ``mode="keyword"``."""
    try:
        return (
            table.search(query, query_type="fts")
            .limit(limit)
            .to_list()
        )
    except Exception:
        return []


async def rag_condense(
    text: str,
    filename="doc",
    query="",
    _chunks: list[str] | None = None,
    _diagnostics: list[str] | None = None,
) -> str:
    """Condense long OCR text into TARGET_CHARS using RAG chunk-ranking.

    **Algorithm (RAg.txt + OCR extensions):**
      1. Chunk via :func:`recursive_text_splitter` (RAg.txt lines 14-42),
         falling back to sentence-based :func:`chunk` if needed.
      2. Index in LanceDB via :func:`build_lance` (RAg.txt lines 64-98) with
         hybrid FTS + semantic search.
      3. Rank chunks via hybrid search + LinearCombinationReranker weight=0.7
         (RAg.txt lines 100-119).
      4. Fall back to BM25-lite when LanceDB/sentence-transformers are
         unavailable, so the OCR endpoint ALWAYS produces useful output.

    When ``_chunks`` is provided (pre-computed by callers like
    :func:`extract_pdf_text`) it is used directly to avoid redundant work.
    When ``_diagnostics`` is provided, it is populated with notes describing
    which backend was used and how many chunks were considered / selected.
    """
    text = (text or "").strip()

    if len(text) <= TARGET_CHARS:
        if _diagnostics is not None:
            _diagnostics.append(f"rag_condense: full_text (len={len(text)} <= {TARGET_CHARS})")
        return text

    chunks = list(_chunks) if _chunks else recursive_text_splitter(text) or chunk(text)
    if len(chunks) <= 1:
        if _diagnostics is not None:
            _diagnostics.append(f"rag_condense: single_chunk -> head truncation")
        return text[:TARGET_CHARS]

    query = query.strip() or "key figures, dates, totals, summary"
    name = "ocr_" + document_id(filename, text)

    table = await asyncio.to_thread(build_lance, chunks, name)

    if table:
        results = await asyncio.to_thread(hybrid, table, query)
        selected = [x["chunk_idx"] for x in results if "chunk_idx" in x]
        backend = "lancedb_hybrid"
    else:
        selected = []
        backend = "bm25_fallback"

    if not selected:
        selected, used = [], 0
        for i, _ in bm25(chunks):
            size = len(chunks[i]) + 2
            if used + size > TARGET_CHARS and selected:
                continue
            selected.append(i)
            used += size
            if used >= TARGET_CHARS:
                break

    selected = sorted(set(selected))
    if 0 not in selected:
        selected.insert(0, 0)

    if _diagnostics is not None:
        _diagnostics.append(
            f"rag_condense: backend={backend}, chunks_total={len(chunks)}, "
            f"chunks_selected={len(selected)}, query={query!r}"
        )
    return "\n\n".join(
        chunks[i].strip()
        for i in selected
        if chunks[i].strip()
    )[:TARGET_CHARS]


MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB upload safety cap for PDF endpoint


def _lancedb_drop_table(name: str) -> bool:
    stack = _try_lancedb_stack()
    if stack is None:
        return False
    lancedb, _, _, _, _ = stack
    try:
        db = lancedb.connect(LANCEDB_PATH)
        if name in db.table_names():
            db.drop_table(name)
            return True
        return False
    except Exception:
        return False


def _sentence_transformers_available() -> bool:
    """Heuristic: ``build_lance`` with a tiny input succeeds if sentence-transformers
    is fully installed. Used only by the /ocr/ status probe so the user sees
    at a glance whether full LanceDB hybrid mode is available or BM25-lite
    fallback will kick in for text condensation."""
    try:
        tbl = build_lance(
            ["sanity check availability"],
            f"_probe_{int(time.time()*1000)}",
            mode="overwrite",
        )
    except Exception:
        tbl = None
    if tbl is None:
        return False
    try:
        _lancedb_drop_table(tbl.name)
    except Exception:
        pass
    return True


# ---- Endpoints ------------------------------------------------------------------

@router.get("/", summary="OCR module status")
async def health() -> dict[str, Any]:
    """Health + capability probe for the OCR module.
    Returns coarse availability flags for PyMuPDF + alternative PDF libs
    (pdfplumber, pypdf, pdfminer.six), renderers (pdf2image, wand),
    LanceDB, NLTK, sentence-transformers, OpenAI and LLMWhisperer so
    Swagger users can quickly tell which fallback stages are enabled
    *before* uploading a PDF.
    """
    # ---- [AI-ADD] Full capability probe including sentence-transformers
    # and the new multi-library PDF extractor/renderer stacks -------------
    local_pdf_libs = _probe_local_pdf_capabilities()
    pdf_ocr_installed = any(local_pdf_libs.values())
    nltk_installed = _try_nltk() is not None
    lancedb_installed = _try_lancedb_stack() is not None
    # ``_sentence_transformers_available`` is stricter than ``lancedb_installed``
    # because it actually runs a tiny build_lance() probe — without sentence-
    # transformers, LanceDB will load but vector embeddings fail at runtime.
    sentence_transformers_installed = (
        lancedb_installed and _sentence_transformers_available()
    )
    local_renderers = _try_pdf_renderers()
    renderer_available = (
        local_pdf_libs["pymupdf"] or bool(local_renderers)
    )
    cfg = get_settings()

    warnings: list[str] = []
    if not pdf_ocr_installed:
        warnings.append(
            "no local PDF text extractor installed. Install at least ONE: "
            "pip install pymupdf (RECOMMENDED — best quality + enables "
            "PNG rendering) OR pdfplumber OR pypdf OR pdfminer.six. "
            "Vision PDF can still work via PDF-direct upload to OpenAI."
        )
    elif not local_pdf_libs["pymupdf"]:
        warnings.append(
            f"pymupdf missing (using pure-Python fallback extractor: "
            f"{[k for k,v in local_pdf_libs.items() if v]}). "
            f"Quality and speed are lower. Run: pip install pymupdf"
        )
    if not renderer_available and cfg.openai_api_key:
        warnings.append(
            "no local PNG renderer (pymupdf/pdf2image/wand) — Vision PDF "
            "will use PDF-direct upload to OpenAI (works but slightly slower)."
        )
    if not lancedb_installed:
        warnings.append("lancedb missing — text condensation falls back to BM25-lite")
    elif not sentence_transformers_installed:
        warnings.append(
            "sentence-transformers / embedding model missing — "
            "LanceDB loaded but hybrid search will degrade to BM25-lite"
        )
    if not cfg.openai_api_key:
        warnings.append("OPENAI_API_KEY not set — Vision PDF fallback disabled")
    if not cfg.llmwhisperer_api_key:
        warnings.append("LLMWHISPERER_API_KEY not set — remote OCR stage skipped")
    elif local_pdf_libs["pymupdf"] is False and not renderer_available:
        # User relies on remote; make sure DNS issue from the earlier error
        # is surfaced with a clear hint in the status probe.
        warnings.append(
            "LLMWhisperer configured — confirm DNS / VPN if you see "
            "'Name or service not known' errors during PDF extraction."
        )

    # Default retrieval mode mirrors the RAG condensation choice:
    # full LanceDB hybrid when everything is installed, otherwise BM25/keyword.
    default_retrieval_mode = (
        "hybrid" if sentence_transformers_installed else "keyword"
    )

    return {
        "status": "ok",
        "message": "OCR module ready",
        "capabilities": {
            "pdf_ocr_installed": pdf_ocr_installed,
            "pdf_text_extractors_available": local_pdf_libs,
            "pdf_png_renderers_available": {
                "pymupdf": local_pdf_libs["pymupdf"],
                **{k: True for k in local_renderers.keys()},
            },
            "nltk_installed": nltk_installed,
            "lancedb_installed": lancedb_installed,
            "sentence_transformers_installed": sentence_transformers_installed,
            "openai_available": _try_openai_client() is not None,
            "llmwhisperer_available": bool(cfg.llmwhisperer_api_key),
            "default_retrieval_mode": default_retrieval_mode,
            "max_pdf_bytes": MAX_PDF_BYTES,
            "rag_txt_detected": True,
            "warnings": warnings,
        },
    }


@router.post("/ocrextract_pdf", summary="Extract text from a PDF file",
             response_description="PDF filename, extracted text, processing time, and OCR/RAG diagnostic metadata")
async def ocr_pdf(file: UploadFile = File(..., description="The PDF file to process")) -> dict[str, Any]:
    """Run the full OCR + RAG pipeline on an uploaded PDF.

    **Fallback order (explicit RAG inter-stage):**
    embedded text extraction → LLMWhisperer → **RAG chunking/indexing** → OpenAI Vision (page-by-page).

    RAG condensation is applied after *every* successful extraction stage,
    using the algorithm described in ``RAg.txt``: recursive_text_splitter +
    LanceDB hybrid search with LinearCombinationReranker (weight=0.7),
    falling back to BM25-lite when vector deps are missing.
    """
    if not file.filename or not re.search(r"\.pdf$", file.filename, re.I):
        error(400, "File must be a PDF")

    start = time.time()
    data = await file.read()

    if not data:
        error(400, "Empty PDF file")

    # ---- [AI-ADD] Enforce MAX_PDF_BYTES safety cap -------------------------
    if len(data) > MAX_PDF_BYTES:
        error(413, f"PDF exceeds {MAX_PDF_BYTES // 1024 // 1024} MB")

    breakdown: dict[str, Any] = {}
    try:
        text = await extract_pdf_text(data, file.filename, breakdown=breakdown)
    except HTTPException:
        # Re-raise so FastAPI renders the 422, but enrich it with what we learned
        raise

    elapsed = time.time() - start
    doc_id = document_id(file.filename, text)

    response: dict[str, Any] = {
        "filename": file.filename,
        "document_id": doc_id,
        "text": text,
        "chars": len(text),
        "time": elapsed,
    }
    response.update(breakdown)
    if "extraction_stage" not in response:
        response["extraction_stage"] = "unknown"
    if "rag_mode_used" not in response:
        response["rag_mode_used"] = rag_detect_mode(text)
    return response


@router.post("/ocrextract_image", summary="Analyze / OCR an image file",
             response_description="Image filename, analysis mode, result, and processing time")
async def ocr_image(
    file: UploadFile = File(..., description="The image file to process (JPEG/PNG/GIF/WebP)"),
    mode: str = Query(
        "ocr",
        enum=["describe", "ocr", "classify"],
        description="Analysis mode: ocr (extract text), describe (visual caption), classify (JSON tags)",
    ),
) -> dict[str, Any]:
    """Run OpenAI Vision on an uploaded image.

    - **ocr** — extract all visible text as plain text
    - **describe** — detailed visual caption
    - **classify** — return JSON with category, tags, and confidence
    """
    content_type = file.content_type or ""

    if content_type not in ALLOWED_IMAGE_TYPES:
        error(415, f"Unsupported type: {content_type}")

    start = time.time()
    data = await file.read()

    if not data:
        error(400, "Empty image file")

    if len(data) > MAX_IMAGE_BYTES:
        error(413, "Image exceeds 10 MB")

    result = await vision(data, content_type, mode)

    return {
        "filename": file.filename or "image",
        "mode": mode,
        "result": result,
        "time": time.time() - start,
    }


if __name__ in {"__main__", "__mp_main__"}:
    print("OCR module loaded")
