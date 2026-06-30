from __future__ import annotations

from datetime import date, datetime, timezone

from kudago_mcp_client.http_client import prepare_params


def test_prepare_params_omits_none_and_encodes_scalars() -> None:
    assert prepare_params({"none": None, "truthy": True, "falsy": False, "number": 10, "text": "msk"}) == {
        "truthy": "true",
        "falsy": "false",
        "number": "10",
        "text": "msk",
    }


def test_prepare_params_encodes_sequences_and_dates() -> None:
    assert prepare_params({
        "fields": ["id", "title", "dates"],
        "ids": [1, 2, 3],
        "day": date(2026, 6, 26),
        "moment": datetime(2026, 6, 26, 12, 30, tzinfo=timezone.utc),
    }) == {
        "fields": "id,title,dates",
        "ids": "1,2,3",
        "day": "2026-06-26",
        "moment": "2026-06-26T12:30:00+00:00",
    }
