from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.contracts import CommandEvent, CommandOutput, ExecutionContext
from app.schemas.routing import TransitRouteRequest
from app.services.transit_routing_service import TransitRoutingService


class TransitRoutingHandler:
    command = "routing.transit.plan"

    def __init__(self, session: AsyncSession) -> None:
        self.routing_service = TransitRoutingService(session)

    async def run(
        self,
        context: ExecutionContext,
        payload: dict[str, Any],
    ) -> CommandOutput:
        request = TransitRouteRequest.model_validate(payload)
        result = await self.routing_service.plan_route(
            job_id=context.job_id,
            request=request,
        )
        return _routing_output(self.command, result)


def _routing_output(command: str, result: dict[str, Any]) -> CommandOutput:
    routes = result.get("routes", [])
    status = str(result["status"])
    events = [
        CommandEvent(
            event_type="routing_request_prepared",
            message="Transit routing request was prepared",
            data={"provider": result["provider"]},
        ),
        CommandEvent(
            event_type=(
                "routing_no_route"
                if status in {"no_route", "coverage_unavailable"}
                else "routing_result_received"
            ),
            message=(
                "Transit routing returned no confirmed route"
                if status in {"no_route", "coverage_unavailable"}
                else "Transit routing result was received"
            ),
            data={"status": status, "returned": result["returned"]},
        ),
        CommandEvent(
            event_type="routing_normalized",
            message="Transit routing result was normalized",
            data={"provider": result["provider"], "returned": result["returned"]},
        ),
    ]
    return CommandOutput(
        status=status,
        result_type=command,
        items=routes,
        meta={
            "status": status,
            "provider": result["provider"],
            "returned": result["returned"],
        },
        result_payload=result,
        events=events,
    )
