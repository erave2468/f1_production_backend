from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import championship, circuit, grandprix, media
from app.config import settings
from app.db import engine

app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(grandprix.router, prefix="/api")
app.include_router(championship.router, prefix="/api")
app.include_router(circuit.router, prefix="/api")
app.include_router(media.router, prefix="/api")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/ready",
    tags=["system"],
    include_in_schema=False,
)
def ready() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ready"}


