from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.executor import CommandExecutor
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.repositories.job_repository import JobRepository
from app.repositories.result_repository import ResultRepository
from app.services.job_service import JobService
from app.services.location_resolver_service import LocationResolverService
from app.services.movie_showings_service import MovieShowingsService
from app.services.movies_service import MoviesService


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
        executor = CommandExecutor(session)

        try:
            output = await executor.run_existing_job(
                parsed_job_id,
                source="worker",
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "geo_status": output.status,
            }
        except ValueError as exc:
            if str(exc).startswith("Job not found:"):
                return {
                    "status": "error",
                    "message": "Job not found",
                    "job_id": job_id,
                }
            await session.commit()
            raise
        except Exception:
            await session.commit()
            raise


async def process_events_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        executor = CommandExecutor(session)

        try:
            output = await executor.run_existing_job(
                parsed_job_id,
                source="worker",
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "result_status": output.status,
            }
        except ValueError as exc:
            if str(exc).startswith("Job not found:"):
                return {
                    "status": "error",
                    "message": "Job not found",
                    "job_id": job_id,
                }
            await session.commit()
            raise
        except Exception:
            await session.commit()
            raise


async def process_places_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        executor = CommandExecutor(session)

        try:
            output = await executor.run_existing_job(
                parsed_job_id,
                source="worker",
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "result_status": output.status,
            }
        except ValueError as exc:
            if str(exc).startswith("Job not found:"):
                return {
                    "status": "error",
                    "message": "Job not found",
                    "job_id": job_id,
                }
            await session.commit()
            raise
        except Exception:
            await session.commit()
            raise


async def process_movie_showings_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        location_resolver = LocationResolverService(session)
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
            place_query = payload.get("place_query")
            resolved = await location_resolver.resolve_for_kudago_location_or_coordinates(
                job_id=job.id,
                place_query=place_query,
                location=payload.get("location"),
                lat=None,
                lon=None,
                radius=None,
                lang=lang,
                allow_coordinates=False,
            )
            location = resolved["location"]
            geo_meta = resolved["geo"]

            if resolved["status"] != "ok":
                result_status = resolved["status"]
                if result_status == "geo_ambiguous":
                    message = (
                        "Geo resolution is ambiguous; specify a KudaGo location "
                        "slug or place_id."
                    )
                elif result_status == "geo_not_found":
                    message = (
                        "Geo resolution found no matching place; specify a KudaGo "
                        "location slug or place_id."
                    )
                else:
                    message = (
                        "KudaGo movie showings endpoint requires a KudaGo location "
                        "slug or place_id. Coordinates are not supported."
                    )
                result_payload = {
                    "status": result_status,
                    "message": message,
                    "geo": geo_meta,
                    "items": [],
                    "count": 0,
                    "returned": 0,
                }
                await result_repo.create(
                    job_id=job.id,
                    result_type="movie_showings.search",
                    items=[],
                    meta={"status": result_status, "geo": geo_meta},
                )
                await job_repo.mark_succeeded(job, result_payload=result_payload)
                await job_repo.add_event(
                    job_id=job.id,
                    event_type="completed",
                    message="Movie showings search completed without KudaGo call",
                    data={"status": result_status},
                )
                await session.commit()
                return {
                    "status": "ok",
                    "job_id": job_id,
                    "result_status": result_status,
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


async def process_movies_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        job_repo = JobRepository(session)
        result_repo = ResultRepository(session)
        location_resolver = LocationResolverService(session)
        movies_service = MoviesService(session)
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
                message="Movies search job started",
                data={"command": job.command},
            )

            payload = job.input_payload
            lang = payload.get("lang") or settings.kudago_lang
            place_query = payload.get("place_query")
            resolved = await location_resolver.resolve_for_kudago_location_or_coordinates(
                job_id=job.id,
                place_query=place_query,
                location=payload.get("location"),
                lat=None,
                lon=None,
                radius=None,
                lang=lang,
                allow_coordinates=False,
            )
            location = resolved["location"]
            geo_meta = resolved["geo"]

            if resolved["status"] != "ok":
                result_status = resolved["status"]
                if result_status == "geo_ambiguous":
                    message = (
                        "Geo resolution is ambiguous; specify a KudaGo location "
                        "slug or place_id."
                    )
                elif result_status == "geo_not_found":
                    message = (
                        "Geo resolution found no matching place; specify a KudaGo "
                        "location slug or place_id."
                    )
                else:
                    message = (
                        "KudaGo movies endpoint requires a KudaGo location slug or "
                        "place_id. Coordinates are not supported."
                    )
                result_payload = {
                    "status": result_status,
                    "message": message,
                    "geo": geo_meta,
                    "items": [],
                    "count": 0,
                    "returned": 0,
                }
                await result_repo.create(
                    job_id=job.id,
                    result_type="movies.search",
                    items=[],
                    meta={"status": result_status, "geo": geo_meta},
                )
                await job_repo.mark_succeeded(job, result_payload=result_payload)
                await job_repo.add_event(
                    job_id=job.id,
                    event_type="completed",
                    message="Movies search completed without KudaGo call",
                    data={"status": result_status},
                )
                await session.commit()
                return {
                    "status": "ok",
                    "job_id": job_id,
                    "result_status": result_status,
                }

            actual_since = payload.get("actual_since")
            actual_until = payload.get("actual_until")

            if actual_since is None and not payload.get("include_past", False):
                actual_since = int(datetime.now(timezone.utc).timestamp())
                await job_repo.add_event(
                    job_id=job.id,
                    event_type="actual_since_defaulted",
                    message=(
                        "actual_since was not provided, defaulted to current "
                        "UTC timestamp"
                    ),
                    data={"actual_since": actual_since},
                )

            search_result = await movies_service.search_movies(
                job_id=job.id,
                location=location,
                place_id=payload.get("place_id"),
                tags=payload.get("tags"),
                is_free=payload.get("is_free"),
                premiering_in_location=payload.get("premiering_in_location"),
                actual_since=actual_since,
                actual_until=actual_until,
                page=payload.get("page", 1),
                page_size=payload.get("page_size", 10),
                lang=lang,
            )
            items = search_result["items"]
            filters = {
                "location": location,
                "place_query": place_query,
                "place_id": payload.get("place_id"),
                "tags": payload.get("tags"),
                "is_free": payload.get("is_free"),
                "premiering_in_location": payload.get("premiering_in_location"),
                "actual_since": actual_since,
                "actual_until": actual_until,
                "include_past": payload.get("include_past", False),
            }
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
                result_type="movies.search",
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
                message="Movies search job completed",
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
                message="Movies search job failed",
                data={
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            await session.commit()
            raise


async def process_news_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        executor = CommandExecutor(session)

        try:
            output = await executor.run_existing_job(
                parsed_job_id,
                source="worker",
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "result_status": output.status,
            }
        except ValueError as exc:
            if str(exc).startswith("Job not found:"):
                return {
                    "status": "error",
                    "message": "Job not found",
                    "job_id": job_id,
                }
            await session.commit()
            raise
        except Exception:
            await session.commit()
            raise


async def process_lists_search_job(ctx, job_id: str) -> dict:
    parsed_job_id = UUID(job_id)

    async with AsyncSessionLocal() as session:
        executor = CommandExecutor(session)

        try:
            output = await executor.run_existing_job(
                parsed_job_id,
                source="worker",
            )
            await session.commit()

            return {
                "status": "ok",
                "job_id": job_id,
                "result_status": output.status,
            }
        except ValueError as exc:
            if str(exc).startswith("Job not found:"):
                return {
                    "status": "error",
                    "message": "Job not found",
                    "job_id": job_id,
                }
            await session.commit()
            raise
        except Exception:
            await session.commit()
            raise
