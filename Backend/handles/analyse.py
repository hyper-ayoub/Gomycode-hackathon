from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.clients import extract_text_from_document, get_openai_client
from core.config import settings
from core.database import Report, get_session

router = APIRouter()

SUMMARY_PROMPT = (
    "You are DarijaDoc. The user uploaded a medical document (lab result, prescription, "
    "or doctor's note). Below is the raw OCR-extracted text. Write a short, plain-language "
    "summary in Darija of what this document says, understandable to someone with no "
    "medical background. Do not invent information that isn't in the text."
)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


class AnalyseResponse(BaseModel):
    report_id: str
    filename: str | None
    extracted_text: str
    summary: str | None


@router.post("", response_model=AnalyseResponse, summary="Upload a medical document for OCR + quick summary")
async def analyse_document(
    file: UploadFile = File(..., description="Image or PDF of a medical document"),
    db: AsyncSession = Depends(get_session),
) -> AnalyseResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB).")

    extracted_text = await extract_text_from_document(content, file.filename)

    summary = None
    if settings.openai_configured and extracted_text:
        client = get_openai_client()
        completion = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": extracted_text},
            ],
        )
        summary = completion.choices[0].message.content

    report = Report(source_filename=file.filename, extracted_text=extracted_text, summary=summary)
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return AnalyseResponse(
        report_id=report.id,
        filename=report.source_filename,
        extracted_text=report.extracted_text,
        summary=report.summary,
    )
