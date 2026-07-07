from typing import Literal

from pydantic import BaseModel, Field, model_validator


ReferenceKind = Literal[
    "event_categories",
    "place_categories",
    "locations",
    "location",
]


class ReferenceGetRequest(BaseModel):
    kind: ReferenceKind
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    lang: str = "ru"

    @model_validator(mode="after")
    def validate_slug(self):
        if self.kind == "location" and self.slug is None:
            raise ValueError("slug is required for kind=location")
        return self


class ObjectDetailRequest(BaseModel):
    object_type: Literal[
        "event",
        "place",
        "movie",
        "movie_showing",
        "news",
        "list",
        "agent",
        "agent_role",
        "location",
    ]
    object_id: str = Field(min_length=1, max_length=100)
    include_comments: bool = False
    include_showings: bool = False
    lang: str = "ru"
