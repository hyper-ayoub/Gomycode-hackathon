from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import init_db
from handles import analyse, chat, deep_analyzed, explain, health, location, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="DarijaDoc API",
    description="Arabic/Darija Voice Medical Navigator — backend API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(analyse.router, prefix="/analyse", tags=["Analyse"])
app.include_router(deep_analyzed.router)  # router already sets prefix="/ocr", tags=["ocr"]
app.include_router(explain.router, prefix="/explain", tags=["Explain"])
app.include_router(location.router, prefix="/location", tags=["Location"])
app.include_router(voice.router, prefix="/voice", tags=["Voice"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
