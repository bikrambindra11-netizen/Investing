"""FastAPI entry point. Run: uvicorn backend.app.main:app --reload"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from .config import settings
from .db import Instrument, SessionLocal, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Stock Picker Portal API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    with SessionLocal() as s:
        instrument_count = s.scalar(select(func.count()).select_from(Instrument))
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "database": "connected",
        "instruments": instrument_count,
        "keys_configured": settings.key_status(),
        "disclaimer": "Personal screening tool. Not investment advice.",
    }
