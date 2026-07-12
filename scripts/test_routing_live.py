import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.integrations.openrouteservice import OpenRouteServiceHttpClient, directions
from app.integrations.transitous import TransitousHttpClient, plan_journey


BERLIN_ALEXANDERPLATZ = (52.5219, 13.4132)
BERLIN_HAUPTBAHNHOF = (52.5251, 13.3694)
SAFE_TRANSIT_MODES = [
    "TRAM",
    "SUBWAY",
    "FERRY",
    "BUS",
    "COACH",
    "RAIL",
    "FUNICULAR",
    "AERIAL_LIFT",
]


async def run_transitous() -> None:
    user_agent = os.getenv("TRANSITOUS_USER_AGENT", "").strip()
    if not user_agent:
        raise RuntimeError(
            "Set TRANSITOUS_USER_AGENT with application name, version and contact"
        )
    base_url = os.getenv("TRANSITOUS_BASE_URL", "https://api.transitous.org/")
    timeout = float(os.getenv("TRANSITOUS_TIMEOUT_SECONDS", "40"))
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    origin = f"{BERLIN_ALEXANDERPLATZ[0]},{BERLIN_ALEXANDERPLATZ[1]}"
    destination = f"{BERLIN_HAUPTBAHNHOF[0]},{BERLIN_HAUPTBAHNHOF[1]}"
    scenarios = [
        ("transit-default", False, SAFE_TRANSIT_MODES),
        ("transit-arrive-by", True, SAFE_TRANSIT_MODES),
        ("transit-restricted", False, ["SUBURBAN", "SUBWAY", "BUS"]),
    ]

    async with TransitousHttpClient(
        base_url=base_url,
        timeout=timeout,
        user_agent=user_agent,
    ) as client:
        for name, arrive_by, modes in scenarios:
            result = await plan_journey(
                client,
                from_place=origin,
                to_place=destination,
                time=tomorrow,
                arrive_by=arrive_by,
                transit_modes=modes,
                max_transfers=None,
                max_travel_time=180,
                min_transfer_time=None,
                num_itineraries=3,
                search_window=900,
                language="en",
            )
            print(f"{name}: itineraries={len(result.get('itineraries', []))}")


async def run_openrouteservice() -> None:
    api_key = os.getenv("OPENROUTESERVICE_API_KEY", "").strip()
    if not api_key:
        print("OpenRouteService live checks skipped: OPENROUTESERVICE_API_KEY is empty")
        return
    base_url = os.getenv(
        "OPENROUTESERVICE_BASE_URL",
        "https://api.openrouteservice.org/",
    )
    timeout = float(os.getenv("OPENROUTESERVICE_TIMEOUT_SECONDS", "30"))
    user_agent = os.getenv(
        "OPENROUTESERVICE_USER_AGENT",
        "kudago-nominatim-service/0.1.0",
    )
    coordinates = [
        [BERLIN_ALEXANDERPLATZ[1], BERLIN_ALEXANDERPLATZ[0]],
        [BERLIN_HAUPTBAHNHOF[1], BERLIN_HAUPTBAHNHOF[0]],
    ]

    async with OpenRouteServiceHttpClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        user_agent=user_agent,
    ) as client:
        for profile in ("foot-walking", "driving-car", "cycling-regular"):
            result = await directions(
                client,
                profile=profile,
                coordinates=coordinates,
                language="en",
                instructions=True,
                geometry=False,
            )
            print(f"ors-{profile}: routes={len(result.get('routes', []))}")


async def main() -> None:
    await run_transitous()
    await run_openrouteservice()


if __name__ == "__main__":
    asyncio.run(main())
