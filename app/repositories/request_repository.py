from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_request import ApiRequest


class RequestRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        endpoint: str,
        method: str,
        request_params: dict[str, Any],
        request_text: str | None = None,
        client_request_id: str | None = None,
    ) -> ApiRequest:
        api_request = ApiRequest(
            endpoint=endpoint,
            method=method,
            request_params=request_params,
            request_text=request_text,
            client_request_id=client_request_id,
            status="received",
        )
        self.session.add(api_request)
        await self.session.flush()
        return api_request
    
    async def get_by_client_request_id(
        self,
        client_request_id: str,
    ) -> ApiRequest | None:
        result = await self.session.execute(
            select(ApiRequest).where(
                ApiRequest.client_request_id == client_request_id
            )
        )
        return result.scalar_one_or_none()