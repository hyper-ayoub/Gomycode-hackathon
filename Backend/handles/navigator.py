"""Routes from darijadoc-ai, served by the same FastAPI app.

The React app keeps /explain, /chat, /voice, and /location. The test bench
keeps /api/ask, /api/rx, /api/tts, /api/pharmacies, /api/hospitals, and the
static page at /. Both use the key in Backend/.env.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from core.config import settings

AI_ROOT = Path(__file__).resolve().parents[2] / "darijadoc-ai"
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

if settings.OPENAI_API_KEY:
    os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

import serve as bench  # noqa: E402
import test_prompt as tp  # noqa: E402

router = APIRouter(tags=["Navigator"])

WEB = AI_ROOT / "web"
VENDOR = WEB / "vendor"
OUTPUTS = AI_ROOT / "outputs"


class _Bench:
    """Call serve.Handler methods without opening a socket."""

    _origin = staticmethod(bench.Handler._origin)
    _expectation = bench.Handler._expectation
    _score = bench.Handler._score
    _pois = bench.Handler._pois
    _ask = bench.Handler._ask
    _rx = bench.Handler._rx


_bench = _Bench()


class PlaceQuery(BaseModel):
    lat: float | None = None
    lng: float | None = None
    city: str | None = None


def _safe_file(root: Path, relative: str) -> Path | None:
    target = (root / relative).resolve()
    if not str(target).startswith(str(root.resolve())) or not target.is_file():
        return None
    return target


def _json_error(exc: Exception, status: int = 500) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
        status_code=status,
    )


@router.get("/api/health")
def navigator_health() -> dict:
    samples = len(__import__("json").loads((tp.TESTS_DIR / "test_inputs.json").read_text("utf-8")))
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "ok": True,
        "api_key": has_key,
        "model": tp.MODEL,
        "samples": samples,
        "tts": has_key,
        "places": True,
    }


@router.get("/api/cities")
def cities() -> list[dict]:
    return [{"name": name, "lat": coords[0], "lng": coords[1]} for name, coords in bench.CITIES.items()]


@router.get("/api/samples")
def samples() -> list[dict]:
    import json

    tests = json.loads((tp.TESTS_DIR / "test_inputs.json").read_text("utf-8"))
    return [
        {
            "id": item["id"],
            "input": item["input"],
            "category": item.get("category", "?"),
            "expect_emergency": item.get("expect_emergency"),
        }
        for item in tests
    ]


@router.get("/api/fixtures")
def fixtures() -> list[dict]:
    import json

    found = json.loads((tp.TESTS_DIR / "fixtures.json").read_text("utf-8"))
    return [
        {
            "name": name,
            "url": "/outputs/" + Path(item["image"]).name,
            "note": item.get("note", ""),
            "unreadable": item.get("unreadable"),
        }
        for name, item in found.items()
    ]


@router.post("/api/ask", response_model=None)
async def ask(payload: dict):
    try:
        return await asyncio.to_thread(_bench._ask, payload)
    except Exception as exc:
        return _json_error(exc)


@router.post("/api/rx", response_model=None)
async def rx(payload: dict):
    try:
        return await asyncio.to_thread(_bench._rx, payload)
    except Exception as exc:
        return _json_error(exc)


@router.post("/api/pharmacies", response_model=None)
async def pharmacies(payload: PlaceQuery):
    out = await asyncio.to_thread(_bench._pois, payload.model_dump(), ("pharmacy",), 3000, 25)
    return JSONResponse(out, status_code=200 if out.get("ok") else 502)


@router.post("/api/hospitals", response_model=None)
async def hospitals(payload: PlaceQuery):
    out = await asyncio.to_thread(
        _bench._pois,
        payload.model_dump(),
        ("hospital",),
        10000,
        15,
        bench.NOT_A_HOSPITAL_RE,
    )
    return JSONResponse(out, status_code=200 if out.get("ok") else 502)


@router.post("/api/tts", response_model=None)
async def tts(payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "nothing to say"}, status_code=400)
    if len(text) > 2000:
        return JSONResponse({"ok": False, "error": "too long to speak"}, status_code=400)
    if not os.getenv("OPENAI_API_KEY"):
        return JSONResponse({"ok": False, "error": "NOT_CONFIGURED"}, status_code=503)

    instructions = (payload.get("instructions") or "").strip() or (
        "Speak Moroccan Darija in Arabic script, slowly and calmly."
    )
    if instructions and len(instructions) > 1000:
        instructions = instructions[:1000]

    def _speak() -> bytes:
        from openai import OpenAI

        kwargs = {
            "model": payload.get("model") or "gpt-4o-mini-tts",
            "voice": payload.get("voice") or "shimmer",
            "input": text,
        }
        if instructions:
            kwargs["instructions"] = instructions
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        try:
            return client.audio.speech.create(**kwargs).read()
        except TypeError:
            kwargs.pop("instructions", None)
            return client.audio.speech.create(**kwargs).read()

    try:
        audio = await asyncio.to_thread(_speak)
    except Exception as exc:
        return _json_error(exc, 502)
    return Response(content=audio, media_type="audio/mpeg")


@router.get("/")
def bench_page() -> FileResponse:
    return FileResponse(WEB / "index.html")


@router.get("/style.css")
def bench_style() -> FileResponse:
    return FileResponse(WEB / "style.css")


@router.get("/app.js")
def bench_app() -> FileResponse:
    return FileResponse(WEB / "app.js")


@router.get("/map.js")
def bench_map() -> FileResponse:
    return FileResponse(WEB / "map.js")


@router.get("/voice.js")
def bench_voice() -> FileResponse:
    return FileResponse(AI_ROOT / "prompts" / "voice.js")


@router.get("/vendor/{file_path:path}")
def vendor_file(file_path: str) -> FileResponse:
    target = _safe_file(VENDOR, file_path)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)


@router.get("/outputs/{file_path:path}")
def output_file(file_path: str) -> FileResponse:
    target = _safe_file(OUTPUTS, file_path)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)
