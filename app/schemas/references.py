from typing import Any

from pydantic import BaseModel


class ReferenceResponse(BaseModel):
    status: str
    kind: str
    data: Any


class LocationReferenceResponse(BaseModel):
    status: str
    kind: str
    slug: str
    data: Any
