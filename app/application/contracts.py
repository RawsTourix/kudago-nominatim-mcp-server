from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(slots=True, frozen=True)
class ExecutionContext:
    job_id: UUID
    command: str
    source: str
    endpoint: str | None = None


@dataclass(slots=True, frozen=True)
class CommandEvent:
    event_type: str
    message: str
    data: dict[str, Any]


@dataclass(slots=True, frozen=True)
class CommandOutput:
    status: str
    result_type: str
    items: list[dict[str, Any]]
    meta: dict[str, Any]
    result_payload: dict[str, Any]
    events: list[CommandEvent] = field(default_factory=list)
