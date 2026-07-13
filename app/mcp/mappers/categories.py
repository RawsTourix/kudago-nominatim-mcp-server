from __future__ import annotations

from enum import StrEnum


def enum_values_to_csv(values: list[StrEnum] | None) -> str | None:
    if values is None:
        return None
    return ",".join(value.value for value in values)


__all__ = ["enum_values_to_csv"]
