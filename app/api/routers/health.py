from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import ArqPool, DbSession


router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    return {"status": "ok"}


@router.get("/db")
async def health_db(session: DbSession):
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.get("/ready")
async def readiness(session: DbSession, redis: ArqPool):
    await session.execute(text("SELECT 1"))
    await redis.ping()
    return {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
    }
