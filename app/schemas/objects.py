from typing import Any

from pydantic import BaseModel


class ObjectDetailResponse(BaseModel):
    status: str
    object_type: str
    object_id: str
    data: Any
    comments: Any | None = None
    showings: Any | None = None
