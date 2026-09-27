import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clients import get_openai_client
from core.config import settings
from core.contract import normalize_chat, parse_json_object
from core.database import ChatMessage, get_session

router = APIRouter()

SYSTEM_PROMPT = (
    "You are DarijaDoc, a warm and patient medical navigator assistant. "
    "Reply in Moroccan Darija by default, matching the script the user used "
    "(Arabic script or Latin/French-transliterated Darija). Keep explanations "
    "simple and reassuring for someone without medical training. You never give "
    "a definitive diagnosis or prescribe medication — you explain, orient, and "
    "always recommend seeing a doctor or pharmacist for anything serious, urgent, "
    "or when medication dosing is involved."
)


class IncomingMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class EmergencyFlag(BaseModel):
    detected: bool
    message: str = ""


class ChatRequest(BaseModel):
    messages: list[IncomingMessage] | None = Field(None, max_length=20)
    language: Literal["fr", "ary"] = "ary"
    context: dict[str, Any] | None = None
    message: str | None = Field(None, min_length=1, description="Single-turn message used by older clients")
    session_id: str | None = Field(None, description="Existing session id to continue a conversation")

    @model_validator(mode="after")
    def has_input(self) -> "ChatRequest":
        if self.messages:
            return self
        if self.message:
            return self
        raise ValueError("Provide messages or message")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    emergency: EmergencyFlag


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatHistoryMessage]


async def get_chat_reply(db: AsyncSession, message: str, session_id: str | None) -> tuple[str, str]:
    """Shared chat pipeline used by both the text chat route and the voice route."""
    session_id = session_id or uuid.uuid4().hex

    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    history = result.scalars().all()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": message})

    client = get_openai_client()
    completion = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
    )
    reply = completion.choices[0].message.content or ""

    db.add(ChatMessage(session_id=session_id, role="user", content=message))
    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
    await db.commit()

    return session_id, reply


def _chat_system(language: str, context: dict[str, Any] | None) -> str:
    lang = "simple French" if language == "fr" else "Moroccan Darija using Arabic script"
    prompt = (
        f"{SYSTEM_PROMPT} Reply in {lang}. "
        "Return one JSON object with keys reply (string) and emergency "
        "({detected: boolean, message: string}). "
        "Set emergency.detected to true only if the user describes chest pain, severe trouble breathing, "
        "signs of stroke, heavy bleeding, loss of consciousness, a severe allergic reaction, "
        "or an intention to harm themselves. Then emergency.message must tell them to contact "
        "emergency services now (Morocco: 141 or 15), and reply stays a short separate note without a diagnosis. "
        "Otherwise detected is false and message is an empty string. "
        "Do not invent doses, schedules, or facts that are not in the conversation or the document context."
    )
    if context:
        snippet = json.dumps(context, ensure_ascii=False)[:6000]
        prompt += " The user already saw this document explanation. Use it and do not contradict it: " + snippet
    return prompt


async def structured_reply(
    history: list[dict[str, str]],
    language: str,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not settings.openai_configured:
        raise HTTPException(status_code=503, detail="NOT_CONFIGURED")

    messages: list[dict[str, Any]] = [{"role": "system", "content": _chat_system(language, context)}]
    messages.extend(history[-12:])
    client = get_openai_client()
    try:
        completion = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="UPSTREAM") from exc

    raw = completion.choices[0].message.content or ""
    try:
        return normalize_chat(parse_json_object(raw), language)
    except (ValueError, json.JSONDecodeError):
        text = raw.strip()
        if not text:
            raise HTTPException(status_code=502, detail="UPSTREAM")
        return {"reply": text, "emergency": {"detected": False, "message": ""}}


@router.post("", response_model=ChatResponse, summary="Send a message to the DarijaDoc chat assistant")
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_session)) -> ChatResponse:
    if payload.messages:
        history = [{"role": item.role, "content": item.content} for item in payload.messages]
        parsed = await structured_reply(history, payload.language, payload.context)
        return ChatResponse(
            session_id=payload.session_id or uuid.uuid4().hex,
            reply=parsed["reply"],
            emergency=EmergencyFlag(**parsed["emergency"]),
        )

    session_id, reply = await get_chat_reply(db, payload.message or "", payload.session_id)
    return ChatResponse(
        session_id=session_id,
        reply=reply,
        emergency=EmergencyFlag(detected=False, message=""),
    )


@router.get("/{session_id}/history", response_model=ChatHistoryResponse, summary="Get chat history for a session")
async def chat_history(session_id: str, db: AsyncSession = Depends(get_session)) -> ChatHistoryResponse:
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    history = result.scalars().all()
    return ChatHistoryResponse(
        session_id=session_id,
        messages=[ChatHistoryMessage(role=m.role, content=m.content) for m in history],
    )
