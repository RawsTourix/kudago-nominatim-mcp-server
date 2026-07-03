import time
from uuid import UUID

from app.integrations.kudago import (
    JsonData,
    KudaGoHttpClient,
    KudaGoResponseError,
    Params,
    prepare_params,
)
from app.repositories.upstream_call_repository import UpstreamCallRepository


class TrackedKudaGoHttpClient(KudaGoHttpClient):
    def __init__(
        self,
        *,
        job_id: UUID,
        upstream_call_repo: UpstreamCallRepository,
        operation_prefix: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.job_id = job_id
        self.upstream_call_repo = upstream_call_repo
        self.operation_prefix = operation_prefix

    async def get(self, path: str, params: Params | None = None) -> JsonData:
        started = time.perf_counter()
        request_payload = prepare_params(params)
        operation_suffix = path.strip("/").replace("/", ".") or "root"
        operation = f"{self.operation_prefix}.{operation_suffix}"
        url_path = f"/{path.lstrip('/')}"

        try:
            data = await super().get(path, params)
        except Exception as exc:
            await self.upstream_call_repo.create(
                job_id=self.job_id,
                provider="kudago",
                operation=operation,
                url_path=url_path,
                request_payload=request_payload,
                response_payload=None,
                response_status_code=(
                    exc.status_code
                    if isinstance(exc, KudaGoResponseError)
                    else None
                ),
                duration_ms=int((time.perf_counter() - started) * 1000),
                success=False,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

        await self.upstream_call_repo.create(
            job_id=self.job_id,
            provider="kudago",
            operation=operation,
            url_path=url_path,
            request_payload=request_payload,
            response_payload=data,
            response_status_code=200,
            duration_ms=int((time.perf_counter() - started) * 1000),
            success=True,
        )
        return data
