from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.references import LocationReferenceResponse, ReferenceResponse
from app.services.reference_service import ReferenceService


router = APIRouter(prefix="/references", tags=["references"])


@router.get("/event-categories", response_model=ReferenceResponse)
async def get_event_categories(session: DbSession, lang: str = "ru"):
    service = ReferenceService(session)
    return await service.get_event_categories(lang=lang)


@router.get("/place-categories", response_model=ReferenceResponse)
async def get_place_categories(session: DbSession, lang: str = "ru"):
    service = ReferenceService(session)
    return await service.get_place_categories(lang=lang)


@router.get("/locations", response_model=ReferenceResponse)
async def get_locations(session: DbSession, lang: str = "ru"):
    service = ReferenceService(session)
    return await service.get_locations(lang=lang)


@router.get("/locations/{slug}", response_model=LocationReferenceResponse)
async def get_location(slug: str, session: DbSession, lang: str = "ru"):
    service = ReferenceService(session)
    return await service.get_location(slug=slug, lang=lang)
