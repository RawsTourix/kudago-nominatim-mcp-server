from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandEvent, CommandOutput, ExecutionContext
from app.schemas.routing import StreetRouteRequest
from app.services.street_routing_service import StreetRoutingService


class StreetRoutingHandler:
    command = "routing.street.plan"

    def __init__(self, session: AsyncSession) -> None:
        self.routing_service = StreetRoutingService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        request = StreetRouteRequest.model_validate(payload)
        result = await self.routing_service.plan_route(
            job_id=context.job_id,
            request=request,
        )
        routes = result.get("routes", [])
        status = str(result["status"])
        events = [
            CommandEvent(
                event_type="routing_request_prepared",
                message="Street routing request was prepared",
                data={"provider": result["provider"], "profile": result["profile"]},
            ),
            CommandEvent(
                event_type=(
                    "routing_no_route"
                    if status == "no_route"
                    else "routing_result_received"
                ),
                message=(
                    "Street routing returned no confirmed route"
                    if status == "no_route"
                    else "Street routing result was received"
                ),
                data={"status": status, "returned": result["returned"]},
            ),
            CommandEvent(
                event_type="routing_normalized",
                message="Street routing result was normalized",
                data={"provider": result["provider"], "returned": result["returned"]},
            ),
        ]
        return CommandOutput(
            status=status,
            result_type=self.command,
            items=routes,
            meta={
                "status": status,
                "provider": result["provider"],
                "profile": result["profile"],
                "returned": result["returned"],
            },
            result_payload=result,
            events=events,
        )
