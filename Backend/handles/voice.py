import base64
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.clients import get_openai_client
from core.config import settings
from core.database import get_session
from handles.chat import get_chat_reply

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class TranscribeResponse(BaseModel):
    text: str


class ConverseResponse(BaseModel):
    session_id: str
    transcript: str
    reply: str
    reply_audio_base64: str | None = None
    reply_audio_format: str | None = None


async def _transcribe(file: UploadFile) -> str:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 20MB).")

    client = get_openai_client()
    buffer = io.BytesIO(content)
    buffer.name = file.filename or "audio.wav"
    transcript = await client.audio.transcriptions.create(
        model=settings.OPENAI_STT_MODEL,
        file=buffer,
    )
    return transcript.text


@router.post("/transcribe", response_model=TranscribeResponse, summary="Transcribe spoken audio to text")
async def transcribe(file: UploadFile = File(..., description="Audio recording (wav/mp3/m4a/webm...)")) -> TranscribeResponse:
    text = await _transcribe(file)
    return TranscribeResponse(text=text)


@router.post(
    "/converse",
    response_model=ConverseResponse,
    summary="Transcribe audio, get a DarijaDoc reply, and optionally synthesize speech back",
)
async def converse(
    file: UploadFile = File(..., description="Audio recording of the user's question"),
    session_id: str | None = None,
    synthesize_speech: bool = True,
    db: AsyncSession = Depends(get_session),
) -> ConverseResponse:
    transcript = await _transcribe(file)
    new_session_id, reply = await get_chat_reply(db, transcript, session_id)

    reply_audio_b64 = None
    reply_audio_format = None
    if synthesize_speech:
        client = get_openai_client()
        speech = await client.audio.speech.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input=reply,
        )
        reply_audio_b64 = base64.b64encode(speech.content).decode("ascii")
        reply_audio_format = "mp3"

    return ConverseResponse(
        session_id=new_session_id,
        transcript=transcript,
        reply=reply,
        reply_audio_base64=reply_audio_b64,
        reply_audio_format=reply_audio_format,
    )
