from fastapi import FastAPI

from app.api.routers import health, jobs
from app.core.config import settings


app = FastAPI(title=settings.app_name)

app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": settings.app_name,
    }