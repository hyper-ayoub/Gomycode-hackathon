import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from core.clients import extract_text_from_document, get_openai_client
from core.config import settings
from core.contract import normalize_explanation, parse_json_object
from core.database import Report, get_session
from handles.documents import MAX_UPLOAD_BYTES, detect_media, pdf_embedded_text, pdf_page_pngs

router = APIRouter()

EXPLAIN_PROMPT = (
    "You are DarijaDoc. Explain the given medical term, phrase, or short passage in very "
    "simple Darija, as if talking to someone with no medical background. Use a short "
    "everyday analogy if it helps. Keep it to a few sentences. If the input already looks "
    "like plain language, just explain what it means for the person's health in practice."
)

DOCUMENT_PROMPT = """You are DarijaDoc. You explain a Moroccan patient's prescription or lab result in plain language.
You never diagnose, never prescribe, and never invent facts that are not visible in the document.

Return one JSON object and nothing else, with exactly these keys:
- document_type: short label such as Ordonnance or Analyse
- summary: a few plain sentences
- items: array of {title, detail} explaining the important lines
- next_steps: array of practical strings that do not create new medical instructions
- uncertainties: array of strings for anything unreadable, missing, or ambiguous
- emergency: {detected: boolean, message: string}
- medicines: array of {name, instructions, dose, times, duration_days}

Rules:
- Write every string in simple French when language is fr.
- Write every string in Moroccan Darija using Arabic script when language is ary.
- Include a medicine only when its name is actually written on the document.
- instructions must come from the document. dose, times, and duration_days must be null unless that exact value is written.
- times, when present, is an array of 24-hour HH:MM strings. Do not convert "matin" or "soir" into a clock time.
- duration_days is an integer only when a number of days is written.
- For lab results with no named medicine, medicines must be [].
- emergency.detected is true only when the document itself says the situation is urgent or tells the person to go to emergency care now. Otherwise detected is false and message is "".
- Use [] for empty lists. Do not add a dose, time, or duration you cannot see.
"""


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1, description="A medical term, phrase, or passage to explain")
    audience: Literal["patient", "caregiver"] = "patient"


class ExplainResponse(BaseModel):
    text: str
    explanation: str


def _require_openai() -> None:
    if not settings.openai_configured:
        raise HTTPException(status_code=503, detail="NOT_CONFIGURED")


def _language_instruction(language: str) -> str:
    if language == "ary":
        return "Language: ary. Write every user-facing string in Moroccan Darija, Arabic script."
    return "Language: fr. Write every user-facing string in simple French."


async def _complete(messages: list[dict[str, Any]]) -> str:
    client = get_openai_client()
    try:
        completion = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="UPSTREAM") from exc
    return completion.choices[0].message.content or ""


async def _explain_term(payload: ExplainRequest) -> ExplainResponse:
    _require_openai()
    client = get_openai_client()
    try:
        completion = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": EXPLAIN_PROMPT},
                {"role": "user", "content": f"Audience: {payload.audience}\nText: {payload.text}"},
            ],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="UPSTREAM") from exc
    explanation = completion.choices[0].message.content or ""
    return ExplainResponse(text=payload.text, explanation=explanation)


async def _from_text(text: str, language: str) -> str:
    clipped = text[:12000]
    return await _complete(
        [
            {"role": "system", "content": DOCUMENT_PROMPT},
            {
                "role": "user",
                "content": f"{_language_instruction(language)}\nDocument text:\n{clipped}",
            },
        ]
    )


async def _from_images(images: list[tuple[bytes, str]], language: str) -> str:
    import base64

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{_language_instruction(language)}\n"
                "These images are the medical document, in page order. "
                "Read them and return the JSON object."
            ),
        }
    ]
    for data, media in images:
        encoded = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media};base64,{encoded}", "detail": "high"},
            }
        )
    return await _complete(
        [
            {"role": "system", "content": DOCUMENT_PROMPT},
            {"role": "user", "content": content},
        ]
    )


async def _read_document(data: bytes, filename: str | None, media: str) -> tuple[str, list[tuple[bytes, str]]]:
    """Return extracted text, or page images when the file is a scan or a photo."""
    if media != "application/pdf":
        return "", [(data, media)]

    text = pdf_embedded_text(data)
    if len(text) >= 80:
        return text, []

    pages = [(png, "image/png") for png in pdf_page_pngs(data)]
    if pages:
        return "", pages

    if settings.llmwhisperer_configured:
        try:
            whispered = await extract_text_from_document(data, filename)
        except HTTPException:
            whispered = ""
        if len(whispered.strip()) >= 15:
            return whispered.strip(), []

    return "", []


async def _explain_document(
    upload: UploadFile,
    language: str,
    db: AsyncSession,
) -> dict[str, Any]:
    if language not in ("fr", "ary"):
        raise HTTPException(status_code=422, detail="UNSUPPORTED_LANGUAGE")

    media = detect_media(upload.filename, upload.content_type)
    if media is None:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_TYPE")

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="EMPTY")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="TOO_LARGE")
    _require_openai()

    text, images = await _read_document(data, upload.filename, media)
    if not text and not images:
        raise HTTPException(status_code=422, detail="UNREADABLE")

    raw = await _from_text(text, language) if text else await _from_images(images, language)
    try:
        normalized = normalize_explanation(parse_json_object(raw), language)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="UPSTREAM") from exc

    try:
        db.add(
            Report(
                source_filename=upload.filename,
                extracted_text=(text or "")[:20000],
                summary=normalized["summary"],
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()

    return normalized


@router.post("", summary="Explain an uploaded document, or a short medical term sent as JSON")
async def explain(request: Request, db: AsyncSession = Depends(get_session)):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = ExplainRequest.model_validate(await request.json())
        except Exception as exc:
            raise HTTPException(status_code=422, detail="INVALID_BODY") from exc
        result = await _explain_term(payload)
        return result.model_dump()

    if "multipart/form-data" not in content_type:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_TYPE")

    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=400, detail="EMPTY")
    raw_language = form.get("language")
    language = raw_language if isinstance(raw_language, str) else "ary"
    return await _explain_document(upload, language, db)
