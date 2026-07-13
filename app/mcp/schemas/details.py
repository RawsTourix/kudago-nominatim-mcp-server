from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


class DetailItemType(StrEnum):
    EVENT = "event"
    PLACE = "place"
    MOVIE = "movie"
    MOVIE_SHOWING = "movie_showing"
    NEWS = "news"
    GUIDE = "guide"


ItemTypeInput = Annotated[
    DetailItemType,
    Field(
        description=(
            "Item kind copied from a previous details_ref: event, place, movie, "
            "movie_showing, news or guide."
        )
    ),
]
ItemIdInput = Annotated[
    str,
    Field(
        description=(
            "Exact KudaGo item identifier copied from a previous MCP result."
        ),
        min_length=1,
        max_length=100,
    ),
]
IncludeCommentsInput = Annotated[
    bool,
    Field(
        description=(
            "Include comments when supported. Valid for event, place, movie, "
            "news and guide; defaults to false."
        )
    ),
]
IncludeShowingsInput = Annotated[
    bool,
    Field(
        description=(
            "Include current showings for a movie. Valid only when item_type is "
            "movie; defaults to false."
        )
    ),
]


class GetDetailsInput(BaseModel):
    item_type: ItemTypeInput
    item_id: ItemIdInput
    include_comments: IncludeCommentsInput = False
    include_showings: IncludeShowingsInput = False

    @model_validator(mode="after")
    def validate_options(self):
        if self.include_showings and self.item_type != DetailItemType.MOVIE:
            raise ValueError("include_showings is valid only for item_type=movie.")
        comment_types = {
            DetailItemType.EVENT,
            DetailItemType.PLACE,
            DetailItemType.MOVIE,
            DetailItemType.NEWS,
            DetailItemType.GUIDE,
        }
        if self.include_comments and self.item_type not in comment_types:
            raise ValueError(
                "include_comments is not supported for this item_type."
            )
        return self


__all__ = [
    "DetailItemType",
    "GetDetailsInput",
    "IncludeCommentsInput",
    "IncludeShowingsInput",
    "ItemIdInput",
    "ItemTypeInput",
]
