from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import events, geo, health, jobs, places, references
from app.core.config import settings
from app.core.redis import close_arq_pool, create_arq_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_redis = await create_arq_pool()
    try:
        yield
    finally:
        await close_arq_pool(app.state.arq_redis)


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(geo.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(places.router, prefix="/api/v1")
app.include_router(references.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": settings.app_name,
    }
