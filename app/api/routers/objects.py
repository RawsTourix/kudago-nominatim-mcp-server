from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession
from app.schemas.objects import ObjectDetailResponse
from app.services.object_service import ObjectService


router = APIRouter(prefix="/objects", tags=["objects"])


@router.get("/{object_type}/{object_id}", response_model=ObjectDetailResponse)
async def get_object_detail(
    object_type: str,
    object_id: str,
    session: DbSession,
    include_comments: bool = False,
    include_showings: bool = False,
    lang: str = "ru",
):
    service = ObjectService(session)

    try:
        return await service.get_object_detail(
            object_type=object_type,
            object_id=object_id,
            include_comments=include_comments,
            include_showings=include_showings,
            lang=lang,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Failed to fetch object from KudaGo",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
        ) from exc
