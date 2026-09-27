import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clients import get_openai_client
from core.config import settings
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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's message")
    session_id: str | None = Field(None, description="Existing session id to continue a conversation")


class ChatResponse(BaseModel):
    session_id: str
    reply: str


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


@router.post("", response_model=ChatResponse, summary="Send a message to the DarijaDoc chat assistant")
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_session)) -> ChatResponse:
    session_id, reply = await get_chat_reply(db, payload.message, payload.session_id)
    return ChatResponse(session_id=session_id, reply=reply)


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
