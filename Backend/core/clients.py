import asyncio

import httpx
from fastapi import HTTPException
from openai import AsyncOpenAI

from core.config import settings


def get_openai_client() -> AsyncOpenAI:
    if not settings.openai_configured:
        raise HTTPException(status_code=503, detail="NOT_CONFIGURED")
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def extract_text_from_document(
    content: bytes,
    filename: str | None = None,
    poll_interval: float = 2.0,
    max_wait_seconds: float = 120.0,
) -> str:
    """Send a document/image to LLMWhisperer OCR (v2 API) and return the extracted text.

    The v2 API is a submit-then-poll job: POST /whisper accepts the file and returns
    a whisper_hash immediately (202), then /whisper-status and /whisper-retrieve are
    polled until the job is processed.
    """
    if not settings.llmwhisperer_configured:
        raise HTTPException(
            status_code=503,
            detail="LLMWHISPERER_API_KEY is not set. Add it to Backend/.env to enable OCR.",
        )

    base_url = settings.LLMWHISPERER_BASE_URL.rstrip("/")
    headers = {"unstract-key": settings.LLMWHISPERER_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            submit = await client.post(
                f"{base_url}/whisper",
                params={"mode": "form", "output_mode": "layout_preserving"},
                headers={**headers, "Content-Type": "application/octet-stream"},
                content=content,
            )
            if submit.status_code not in (200, 202):
                raise HTTPException(
                    status_code=502,
                    detail=f"OCR provider returned {submit.status_code}: {submit.text[:300]}",
                )
            whisper_hash = submit.json().get("whisper_hash")
            if not whisper_hash:
                raise HTTPException(status_code=502, detail="OCR provider did not return a job id.")

            elapsed = 0.0
            while elapsed < max_wait_seconds:
                status_resp = await client.get(
                    f"{base_url}/whisper-status", params={"whisper_hash": whisper_hash}, headers=headers
                )
                status_resp.raise_for_status()
                status = status_resp.json().get("status")
                if status == "processed":
                    break
                if status in ("error", "failed"):
                    raise HTTPException(status_code=502, detail=f"OCR job failed: {status_resp.text[:300]}")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            else:
                raise HTTPException(status_code=504, detail="OCR job timed out.")

            retrieve = await client.get(
                f"{base_url}/whisper-retrieve", params={"whisper_hash": whisper_hash}, headers=headers
            )
            retrieve.raise_for_status()
            data = retrieve.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach OCR provider: {exc}") from exc

    text = data.get("result_text") or data.get("extraction", {}).get("result_text") or ""
    return text.strip()
