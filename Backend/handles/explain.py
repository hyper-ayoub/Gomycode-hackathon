from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.clients import get_openai_client
from core.config import settings

router = APIRouter()

EXPLAIN_PROMPT = (
    "You are DarijaDoc. Explain the given medical term, phrase, or short passage in very "
    "simple Darija, as if talking to someone with no medical background. Use a short "
    "everyday analogy if it helps. Keep it to a few sentences. If the input already looks "
    "like plain language, just explain what it means for the person's health in practice."
)


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1, description="A medical term, phrase, or passage to explain")
    audience: Literal["patient", "caregiver"] = "patient"


class ExplainResponse(BaseModel):
    text: str
    explanation: str


@router.post("", response_model=ExplainResponse, summary="Explain a medical term or passage in simple Darija")
async def explain(payload: ExplainRequest) -> ExplainResponse:
    client = get_openai_client()
    completion = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": EXPLAIN_PROMPT},
            {"role": "user", "content": f"Audience: {payload.audience}\nText: {payload.text}"},
        ],
    )
    explanation = completion.choices[0].message.content or ""
    return ExplainResponse(text=payload.text, explanation=explanation)
