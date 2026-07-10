from datetime import datetime
from typing import Any

from .http_client import TransitousHttpClient, TransitousInvalidResponseError


async def plan_journey(
    client: TransitousHttpClient,
    *,
    from_place: str,
    to_place: str,
    time: datetime | None,
    arrive_by: bool,
    transit_modes: list[str],
    max_transfers: int | None,
    max_travel_time: int | None,
    min_transfer_time: int | None,
    num_itineraries: int,
    search_window: int,
    language: str | None,
) -> dict[str, Any]:
    data = await client.get(
        "/api/v6/plan",
        {
            "fromPlace": from_place,
            "toPlace": to_place,
            "time": time,
            "arriveBy": arrive_by,
            "transitModes": transit_modes,
            "maxTransfers": max_transfers,
            "maxTravelTime": max_travel_time,
            "minTransferTime": min_transfer_time,
            "numItineraries": num_itineraries,
            "maxItineraries": num_itineraries,
            "searchWindow": search_window,
            "language": language,
            "preTransitModes": "WALK",
            "postTransitModes": "WALK",
            "directModes": "",
            "detailedLegs": False,
            "detailedTransfers": False,
            "timetableView": True,
        },
    )
    if not isinstance(data, dict):
        raise TransitousInvalidResponseError(
            "Transitous plan response must be a JSON object"
        )
    return data
