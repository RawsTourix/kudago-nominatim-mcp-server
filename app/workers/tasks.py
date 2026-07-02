from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository
from app.services.events_service import EventsService
from app.services.geo_service import GeoService
from app.services.job_service import JobService
from app.services.movie_showings_service import MovieShowingsService
from app.services.places_service import PlacesService


async def process_test_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        service = JobService(session)
        job_repo = JobRepository(session)

        job = await job_repo.get_by_id(parsed_job_id)

        if job is None:
            return {
                "status": "error",
                "message": "Job not found",
                "job_id": job_id,
            }

        if job.status == "succeeded":
            return {
                "status": "ok",
                "message": "Job already succeeded",
                "job_id": job_id,
            }

        try:
            job = await service.run_test_job(parsed_job_id)
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "job_status": job.status if job else None,
            }

        except Exception as exc:
            if job is not None:
                await job_repo.mark_failed(
                    job,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )

                await job_repo.add_event(
                    job_id=job.id,
                    event_type="failed",
                    message="Worker task failed",
                    data={
                        "error_type": exc.__class__.__name__,
                        "error_message": str(exc),
                    },
                )

            await session.commit()
            raise


async def process_geo_resolve_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        geo_service = GeoService(session)
        job = await job_repo.get_by_id(parsed_job_id)

        if job is None:
            return {
                "status": "error",
                "message": "Job not found",
                "job_id": job_id,
            }

        if job.status == "succeeded":
            return {
                "status": "ok",
                "message": "Job already succeeded",
                "job_id": job_id,
            }

        try:
            await job_repo.mark_running(job)
            await job_repo.add_event(
                job_id=job.id,
                event_type="started",
                message="Geo resolve job started",
                data={"command": job.command},
            )

            payload = job.input_payload
            result_payload = await geo_service.resolve_place(
                job_id=job.id,
                query=payload["query"],
                countrycodes=payload.get("countrycodes", "ru"),
                limit=payload.get("limit", 5),
                accept_language=payload.get("accept_language", "ru"),
            )

            await result_repo.create(
                job_id=job.id,
                result_type="geo.resolve",
                items=result_payload.get("candidates", []),
                meta={
                    "status": result_payload["status"],
                    "source": result_payload["source"],
                    "query": result_payload["query"],
                    "selected_lat": result_payload.get("selected_lat"),
                    "selected_lon": result_payload.get("selected_lon"),
                    "radius": result_payload.get("radius"),
                },
            )
            await job_repo.mark_succeeded(job, result_payload=result_payload)
            await job_repo.add_event(
                job_id=job.id,
                event_type="completed",
                message="Geo resolve job completed",
                data={
                    "geo_status": result_payload["status"],
                    "source": result_payload["source"],
                },
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "geo_status": result_payload["status"],
            }
        except Exception as exc:
            await job_repo.mark_failed(
                job,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            await job_repo.add_event(
                job_id=job.id,
                event_type="failed",
                message="Geo resolve job failed",
                data={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            await session.commit()
            raise


async def process_events_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        events_service = EventsService(session)
        geo_service = GeoService(session)
        job = await job_repo.get_by_id(parsed_job_id)

        if job is None:
            return {"status": "error", "message": "Job not found", "job_id": job_id}

        if job.status == "succeeded":
            return {
                "status": "ok",
                "message": "Job already succeeded",
                "job_id": job_id,
            }

        try:
            await job_repo.mark_running(job)
            await job_repo.add_event(
                job_id=job.id,
                event_type="started",
                message="Events search job started",
                data={"command": job.command},
            )

            payload = job.input_payload
            lang = payload.get("lang") or settings.kudago_lang
            geo_meta: dict | None = None
            location = payload.get("location")
            lat = payload.get("lat")
            lon = payload.get("lon")
            radius = payload.get("radius")
            place_query = payload.get("place_query")

            if place_query and not location and lat is None:
                matched_location = await events_service.find_kudago_location(
                    job_id=job.id,
                    place_query=place_query,
                    lang=lang,
                )

                if matched_location is not None:
                    location = matched_location.get("slug")
                    geo_meta = {
                        "status": "ok",
                        "kind": "kudago_location",
                        "location": location,
                        "matched_location": matched_location,
                    }
                else:
                    geo_result = await geo_service.resolve_place(
                        job_id=job.id,
                        query=place_query,
                        countrycodes=settings.nominatim_countrycodes,
                        limit=5,
                        accept_language=lang,
                    )
                    geo_meta = {
                        "status": geo_result["status"],
                        "kind": (
                            "coordinates" if geo_result["status"] == "ok" else "none"
                        ),
                        "source": geo_result["source"],
                        "query": place_query,
                        "candidates": geo_result.get("candidates", []),
                        "selected_lat": geo_result.get("selected_lat"),
                        "selected_lon": geo_result.get("selected_lon"),
                        "radius": geo_result.get("radius"),
                    }

                    if geo_result["status"] != "ok":
                        result_status = (
                            "geo_ambiguous"
                            if geo_result["status"] == "ambiguous"
                            else "geo_not_found"
                        )
                        result_payload = {
                            "status": result_status,
                            "message": (
                                "Geo resolution did not produce a single coordinate result"
                            ),
                            "geo": geo_meta,
                            "items": [],
                            "count": 0,
                            "returned": 0,
                        }
                        await result_repo.create(
                            job_id=job.id,
                            result_type="events.search",
                            items=[],
                            meta={"status": result_status, "geo": geo_meta},
                        )
                        await job_repo.mark_succeeded(job, result_payload=result_payload)
                        await job_repo.add_event(
                            job_id=job.id,
                            event_type="completed",
                            message=(
                                "Events search completed without KudaGo call because "
                                "geo is ambiguous or not found"
                            ),
                            data={"status": result_status},
                        )
                        await session.commit()
                        return {
                            "status": "ok",
                            "job_id": job_id,
                            "result_status": result_status,
                        }

                    lat = geo_result["selected_lat"]
                    lon = geo_result["selected_lon"]
                    radius = geo_result["radius"] or settings.default_radius
            elif location:
                geo_meta = {
                    "status": "ok",
                    "kind": "kudago_location",
                    "location": location,
                }
            elif lat is not None and lon is not None and radius is not None:
                geo_meta = {
                    "status": "ok",
                    "kind": "coordinates",
                    "lat": lat,
                    "lon": lon,
                    "radius": radius,
                }

            actual_since = payload.get("actual_since")
            actual_until = payload.get("actual_until")

            if actual_since is None and not payload.get("include_past", False):
                actual_since = int(datetime.now(timezone.utc).timestamp())
                await job_repo.add_event(
                    job_id=job.id,
                    event_type="actual_since_defaulted",
                    message=(
                        "actual_since was not provided, defaulted to current UTC timestamp"
                    ),
                    data={"actual_since": actual_since},
                )

            filters = {
                "actual_since": actual_since,
                "actual_until": actual_until,
                "include_past": payload.get("include_past", False),
                "categories": payload.get("categories"),
                "tags": payload.get("tags"),
                "is_free": payload.get("is_free"),
            }

            search_result = await events_service.search_events(
                job_id=job.id,
                location=location,
                lat=lat,
                lon=lon,
                radius=radius,
                actual_since=actual_since,
                actual_until=actual_until,
                categories=payload.get("categories"),
                tags=payload.get("tags"),
                is_free=payload.get("is_free"),
                page=payload.get("page", 1),
                page_size=payload.get("page_size", 10),
                lang=lang,
            )
            items = search_result["items"]
            result_payload = {
                "status": "ok",
                "source": "kudago",
                "geo": geo_meta,
                "filters": filters,
                "count": search_result.get("count"),
                "returned": search_result.get("returned"),
                "items": items,
            }
            await result_repo.create(
                job_id=job.id,
                result_type="events.search",
                items=items,
                meta={
                    "status": "ok",
                    "source": "kudago",
                    "geo": geo_meta,
                    "filters": filters,
                    "count": search_result.get("count"),
                    "returned": search_result.get("returned"),
                },
            )
            await job_repo.mark_succeeded(job, result_payload=result_payload)
            await job_repo.add_event(
                job_id=job.id,
                event_type="completed",
                message="Events search job completed",
                data={
                    "status": "ok",
                    "returned": search_result.get("returned"),
                    "count": search_result.get("count"),
                },
            )
            await session.commit()
            return {
                "status": "ok",
                "job_id": job_id,
                "returned": search_result.get("returned"),
            }
        except Exception as exc:
            await job_repo.mark_failed(
                job,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            await job_repo.add_event(
                job_id=job.id,
                event_type="failed",
                message="Events search job failed",
                data={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            await session.commit()
            raise


async def process_places_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        events_service = EventsService(session)
        geo_service = GeoService(session)
        places_service = PlacesService(session)
        job = await job_repo.get_by_id(parsed_job_id)

        if job is None:
            return {"status": "error", "message": "Job not found", "job_id": job_id}

        if job.status == "succeeded":
            return {
                "status": "ok",
                "message": "Job already succeeded",
                "job_id": job_id,
            }

        try:
            await job_repo.mark_running(job)
            await job_repo.add_event(
                job_id=job.id,
                event_type="started",
                message="Places search job started",
                data={"command": job.command},
            )

            payload = job.input_payload
            lang = payload.get("lang") or settings.kudago_lang
            geo_meta: dict | None = None
            location = payload.get("location")
            lat = payload.get("lat")
            lon = payload.get("lon")
            radius = payload.get("radius")
            place_query = payload.get("place_query")

            if place_query and not location and lat is None:
                matched_location = await events_service.find_kudago_location(
                    job_id=job.id,
                    place_query=place_query,
                    lang=lang,
                )

                if matched_location is not None:
                    location = matched_location.get("slug")
                    geo_meta = {
                        "status": "ok",
                        "kind": "kudago_location",
                        "location": location,
                        "matched_location": matched_location,
                    }
                else:
                    geo_result = await geo_service.resolve_place(
                        job_id=job.id,
                        query=place_query,
                        countrycodes=settings.nominatim_countrycodes,
                        limit=5,
                        accept_language=lang,
                    )
                    geo_meta = {
                        "status": geo_result["status"],
                        "kind": (
                            "coordinates" if geo_result["status"] == "ok" else "none"
                        ),
                        "source": geo_result["source"],
                        "query": place_query,
                        "candidates": geo_result.get("candidates", []),
                        "selected_lat": geo_result.get("selected_lat"),
                        "selected_lon": geo_result.get("selected_lon"),
                        "radius": geo_result.get("radius"),
                    }

                    if geo_result["status"] != "ok":
                        result_status = (
                            "geo_ambiguous"
                            if geo_result["status"] == "ambiguous"
                            else "geo_not_found"
                        )
                        result_payload = {
                            "status": result_status,
                            "message": (
                                "Geo resolution did not produce a single coordinate result"
                            ),
                            "geo": geo_meta,
                            "items": [],
                            "count": 0,
                            "returned": 0,
                        }
                        await result_repo.create(
                            job_id=job.id,
                            result_type="places.search",
                            items=[],
                            meta={"status": result_status, "geo": geo_meta},
                        )
                        await job_repo.mark_succeeded(job, result_payload=result_payload)
                        await job_repo.add_event(
                            job_id=job.id,
                            event_type="completed",
                            message=(
                                "Places search completed without KudaGo call because "
                                "geo is ambiguous or not found"
                            ),
                            data={"status": result_status},
                        )
                        await session.commit()
                        return {
                            "status": "ok",
                            "job_id": job_id,
                            "result_status": result_status,
                        }

                    lat = geo_result["selected_lat"]
                    lon = geo_result["selected_lon"]
                    radius = geo_result["radius"] or settings.default_radius
            elif location:
                geo_meta = {
                    "status": "ok",
                    "kind": "kudago_location",
                    "location": location,
                }
            elif lat is not None and lon is not None and radius is not None:
                geo_meta = {
                    "status": "ok",
                    "kind": "coordinates",
                    "lat": lat,
                    "lon": lon,
                    "radius": radius,
                }

            showing_since = payload.get("showing_since")
            showing_until = payload.get("showing_until")

            if (
                payload.get("has_showings") is True
                and showing_since is None
                and showing_until is None
            ):
                now = datetime.now(timezone.utc)
                showing_since = int(now.timestamp())
                showing_until = int((now + timedelta(days=7)).timestamp())

                await job_repo.add_event(
                    job_id=job.id,
                    event_type="showing_window_defaulted",
                    message=(
                        "showing_since/showing_until were not provided, "
                        "defaulted to next 7 days"
                    ),
                    data={
                        "showing_since": showing_since,
                        "showing_until": showing_until,
                    },
                )

            filters = {
                "categories": payload.get("categories"),
                "tags": payload.get("tags"),
                "has_showings": payload.get("has_showings"),
                "showing_since": showing_since,
                "showing_until": showing_until,
            }
            search_result = await places_service.search_places(
                job_id=job.id,
                location=location,
                lat=lat,
                lon=lon,
                radius=radius,
                categories=payload.get("categories"),
                tags=payload.get("tags"),
                has_showings=payload.get("has_showings"),
                showing_since=showing_since,
                showing_until=showing_until,
                page=payload.get("page", 1),
                page_size=payload.get("page_size", 10),
                lang=lang,
            )
            items = search_result["items"]
            result_payload = {
                "status": "ok",
                "source": "kudago",
                "geo": geo_meta,
                "filters": filters,
                "count": search_result.get("count"),
                "returned": search_result.get("returned"),
                "items": items,
            }
            await result_repo.create(
                job_id=job.id,
                result_type="places.search",
                items=items,
                meta={
                    "status": "ok",
                    "source": "kudago",
                    "geo": geo_meta,
                    "filters": filters,
                    "count": search_result.get("count"),
                    "returned": search_result.get("returned"),
                },
            )
            await job_repo.mark_succeeded(job, result_payload=result_payload)
            await job_repo.add_event(
                job_id=job.id,
                event_type="completed",
                message="Places search job completed",
                data={
                    "status": "ok",
                    "returned": search_result.get("returned"),
                    "count": search_result.get("count"),
                },
            )
            await session.commit()
            return {
                "status": "ok",
                "job_id": job_id,
                "returned": search_result.get("returned"),
            }
        except Exception as exc:
            await job_repo.mark_failed(
                job,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            await job_repo.add_event(
                job_id=job.id,
                event_type="failed",
                message="Places search job failed",
                data={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            await session.commit()
            raise


async def process_movie_showings_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        events_service = EventsService(session)
        geo_service = GeoService(session)
        movie_showings_service = MovieShowingsService(session)
        job = await job_repo.get_by_id(parsed_job_id)

        if job is None:
            return {
                "status": "error",
                "message": "Job not found",
                "job_id": job_id,
            }

        if job.status == "succeeded":
            return {
                "status": "ok",
                "message": "Job already succeeded",
                "job_id": job_id,
            }

        try:
            await job_repo.mark_running(job)
            await job_repo.add_event(
                job_id=job.id,
                event_type="started",
                message="Movie showings search job started",
                data={"command": job.command},
            )

            payload = job.input_payload
            lang = payload.get("lang") or settings.kudago_lang
            location = payload.get("location")
            place_query = payload.get("place_query")
            geo_meta: dict | None = None

            if place_query and not location:
                matched_location = await events_service.find_kudago_location(
                    job_id=job.id,
                    place_query=place_query,
                    lang=lang,
                )

                if matched_location is not None:
                    location = matched_location.get("slug")
                    geo_meta = {
                        "status": "ok",
                        "kind": "kudago_location",
                        "location": location,
                        "matched_location": matched_location,
                    }
                else:
                    geo_result = await geo_service.resolve_place(
                        job_id=job.id,
                        query=place_query,
                        countrycodes=settings.nominatim_countrycodes,
                        limit=5,
                        accept_language=lang,
                    )
                    geo_meta = {
                        "status": geo_result["status"],
                        "kind": "none",
                        "source": geo_result["source"],
                        "query": place_query,
                        "candidates": geo_result.get("candidates", []),
                    }
                    result_payload = {
                        "status": "geo_unsupported",
                        "message": (
                            "KudaGo movie showings endpoint requires a KudaGo "
                            "location slug or place_id. Coordinates are not supported."
                        ),
                        "geo": geo_meta,
                        "items": [],
                        "count": 0,
                        "returned": 0,
                    }
                    await result_repo.create(
                        job_id=job.id,
                        result_type="movie_showings.search",
                        items=[],
                        meta={
                            "status": result_payload["status"],
                            "geo": geo_meta,
                        },
                    )
                    await job_repo.mark_succeeded(job, result_payload=result_payload)
                    await job_repo.add_event(
                        job_id=job.id,
                        event_type="completed",
                        message=(
                            "Movie showings search completed without KudaGo call "
                            "because coordinates are unsupported"
                        ),
                        data={"status": result_payload["status"]},
                    )
                    await session.commit()
                    return {
                        "status": "ok",
                        "job_id": job_id,
                        "result_status": result_payload["status"],
                    }
            elif location:
                geo_meta = {
                    "status": "ok",
                    "kind": "kudago_location",
                    "location": location,
                }

            actual_since = payload.get("actual_since")
            actual_until = payload.get("actual_until")

            if actual_since is None and actual_until is None:
                now = datetime.now(timezone.utc)
                actual_since = int(now.timestamp())
                actual_until = int((now + timedelta(days=7)).timestamp())
                await job_repo.add_event(
                    job_id=job.id,
                    event_type="actual_window_defaulted",
                    message=(
                        "actual_since/actual_until were not provided, "
                        "defaulted to next 7 days"
                    ),
                    data={
                        "actual_since": actual_since,
                        "actual_until": actual_until,
                    },
                )

            filters = {
                "movie_id": payload.get("movie_id"),
                "location": location,
                "place_query": place_query,
                "place_id": payload.get("place_id"),
                "actual_since": actual_since,
                "actual_until": actual_until,
                "is_free": payload.get("is_free"),
            }
            search_result = await movie_showings_service.search_movie_showings(
                job_id=job.id,
                movie_id=payload.get("movie_id"),
                location=location,
                actual_since=actual_since,
                actual_until=actual_until,
                place_id=payload.get("place_id"),
                is_free=payload.get("is_free"),
                page=payload.get("page", 1),
                page_size=payload.get("page_size", 10),
                lang=lang,
            )
            items = search_result["items"]
            result_payload = {
                "status": "ok",
                "source": "kudago",
                "geo": geo_meta,
                "filters": filters,
                "count": search_result.get("count"),
                "returned": search_result.get("returned"),
                "items": items,
            }
            await result_repo.create(
                job_id=job.id,
                result_type="movie_showings.search",
                items=items,
                meta={
                    "status": "ok",
                    "source": "kudago",
                    "geo": geo_meta,
                    "filters": filters,
                    "count": search_result.get("count"),
                    "returned": search_result.get("returned"),
                },
            )
            await job_repo.mark_succeeded(job, result_payload=result_payload)
            await job_repo.add_event(
                job_id=job.id,
                event_type="completed",
                message="Movie showings search job completed",
                data={
                    "status": "ok",
                    "returned": search_result.get("returned"),
                    "count": search_result.get("count"),
                },
            )
            await session.commit()
            return {
                "status": "ok",
                "job_id": job_id,
                "returned": search_result.get("returned"),
            }
        except Exception as exc:
            await job_repo.mark_failed(
                job,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            await job_repo.add_event(
                job_id=job.id,
                event_type="failed",
                message="Movie showings search job failed",
                data={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            await session.commit()
            raise
