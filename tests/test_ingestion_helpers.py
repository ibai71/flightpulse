import json
from pathlib import Path

import pytest

from flightpulse.ingestion.adsb import flatten_flight
from flightpulse.ingestion.bts import month_sequence


def test_month_sequence_includes_end_and_crosses_year():
    assert month_sequence("2025-11", "2026-02") == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)
    ]


@pytest.mark.parametrize("start,end", [("2026-13", "2026-12"), ("2026-07", "2026-05"), ("202605", "2026-07"), ("1986-12", "1987-01")])
def test_month_sequence_rejects_invalid_ranges(start, end):
    with pytest.raises(ValueError):
        month_sequence(start, end)


def test_adsb_flatten_preserves_coordinates_and_time_series():
    fixture = Path(__file__).parent / "fixtures" / "adsb_flight.json"
    events = flatten_flight(json.loads(fixture.read_text(encoding="utf-8")))
    assert len(events) == 2
    assert events[0]["longitude"] == -73.78
    assert events[0]["latitude"] == 40.64
    assert events[0]["altitude_ft"] == 1200
    assert events[0]["ground_speed_knots"] == 180
    assert events[1]["track_deg"] == 92
    assert events[0]["event_ts"].endswith("+00:00")


def test_adsb_flatten_preserves_coordinates_for_stream_validation():
    flight = {
        "flight_id": "x",
        "path": {"type": "LineString", "coordinates": [[181, 40, 5000], [-73, 40, 5000]]},
        "timestamps": [1777550400, 1777550460],
    }
    events = flatten_flight(flight)
    assert len(events) == 2  # geographic range is checked by the streaming quality stage
