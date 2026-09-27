from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import init_db
from handles import analyse, chat, deep_analyzed, explain, health, location, navigator, voice


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

_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _cors_origins() -> list[str]:
    origins: list[str] = []
    for origin in [*_DEV_ORIGINS, settings.FRONTEND_ORIGIN.strip().rstrip("/")]:
        if origin and origin not in origins:
            origins.append(origin)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"
        if settings.APP_ENV == "development"
        else None
    ),
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
app.include_router(navigator.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
