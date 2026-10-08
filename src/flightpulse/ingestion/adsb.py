from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flightpulse.config import data_dir


API_BASE = "https://adsb.aero/api/v1"


def _session() -> requests.Session:
    retry = Retry(total=4, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET", "POST"))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "FlightPulse data engineering portfolio/0.1"})
    return session


def _flatten_pairs(value: object) -> dict[int, float | str]:
    """Flatten nested [epoch, value] trajectory series into an epoch map."""
    result: dict[int, float | str] = {}

    def visit(item: object) -> None:
        if not isinstance(item, list):
            return
        if len(item) == 2 and isinstance(item[0], (int, float)) and isinstance(item[1], (int, float, str)):
            result[int(item[0])] = item[1]
            return
        for child in item:
            visit(child)

    visit(value)
    return result


def flatten_flight(flight: dict[str, object]) -> list[dict[str, object]]:
    path = flight.get("path") or {}
    coords = path.get("coordinates", []) if isinstance(path, dict) else []
    timestamps = flight.get("timestamps") or []
    if not coords or not timestamps:
        return []
    if isinstance(path, dict) and path.get("type") == "LineString":
        coord_segments = [coords]
    else:
        coord_segments = coords
    timestamp_segments = timestamps if timestamps and isinstance(timestamps[0], list) else [timestamps]
    tracks = _flatten_pairs(flight.get("path_tracks"))
    speeds = _flatten_pairs(flight.get("path_gs"))
    vertical_rates = _flatten_pairs(flight.get("path_vr"))
    indicated_speeds = _flatten_pairs(flight.get("path_ias"))
    agl_heights = _flatten_pairs(flight.get("path_agl_ft"))
    events: list[dict[str, object]] = []

    for segment_index, segment in enumerate(coord_segments):
        if segment_index >= len(timestamp_segments):
            break
        segment_times = timestamp_segments[segment_index]
        if not isinstance(segment, list) or not isinstance(segment_times, list):
            continue
        for point_index, point in enumerate(segment):
            if point_index >= len(segment_times) or not isinstance(point, list) or len(point) < 2:
                continue
            try:
                epoch = int(segment_times[point_index])
                longitude, latitude = float(point[0]), float(point[1])
            except (TypeError, ValueError, OverflowError):
                continue
            altitude = point[2] if len(point) > 2 else None
            event = {
                "flight_id": flight.get("flight_id"),
                "icao24": flight.get("icao24"),
                "callsign": flight.get("callsign"),
                "icao_type": flight.get("icao_type"),
                "operator_name": flight.get("operator"),
                "start_airport_ident": flight.get("start_airport_ident"),
                "end_airport_ident": flight.get("end_airport_ident"),
                "event_ts": datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds"),
                "event_epoch": epoch,
                "longitude": longitude,
                "latitude": latitude,
                "altitude_ft": altitude,
                "track_deg": tracks.get(epoch),
                "ground_speed_knots": speeds.get(epoch),
                "vertical_rate_fpm": vertical_rates.get(epoch),
                "indicated_airspeed_knots": indicated_speeds.get(epoch),
                "height_agl_ft": agl_heights.get(epoch),
            }
            if math.isfinite(longitude) and math.isfinite(latitude):
                events.append(event)
    return events


def _airport_geometry(session: requests.Session, airport: str) -> tuple[dict[str, object], set[str]]:
    response = session.get(f"{API_BASE}/airports/{quote(airport, safe='')}", timeout=(10, 45))
    response.raise_for_status()
    result = response.json()
    codes = {str(result.get("ident", "")).upper(), str(result.get("iata_code", "")).upper()}
    codes.discard("")
    airspaces = result.get("airspaces") or []
    if airspaces and airspaces[0].get("geometry"):
        return airspaces[0]["geometry"], codes
    return {
        "type": "Circle",
        "coordinates": [float(result["lon"]), float(result["lat"])],
        "radius": 3000,
    }, codes


def fetch_adsb(airport: str, day: str, max_flights: int | None = None, root: Path | None = None) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9]{2,8}", airport):
        raise ValueError("airport must be a 2–8 character ICAO or IATA code")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("ADS-B date must use YYYY-MM-DD format")
    try:
        requested_day = date.fromisoformat(day)
    except ValueError as error:
        raise ValueError("ADS-B date must use YYYY-MM-DD format") from error
    if max_flights is None:
        max_flights = int(os.getenv("ADS_B_MAX_FLIGHTS", "40"))
    if not 1 <= max_flights <= 1000:
        raise ValueError("max_flights must be between 1 and 1000")
    root = root or data_dir()
    session = _session()
    geometry, airport_codes = _airport_geometry(session, airport.upper())
    start = datetime.combine(requested_day, dt_time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    query = {
        "start_from": start.isoformat().replace("+00:00", "Z"),
        "end_date": end.isoformat().replace("+00:00", "Z"),
        "window_days": 1,
        "limit": min(max_flights, 1000),
        "include_path": True,
        "match": {"endpoint_within": {"mode": "either", "geometry": geometry}},
    }
    flights: list[dict[str, object]] = []
    cursor: str | None = None
    while len(flights) < max_flights:
        if cursor:
            query["cursor"] = cursor
        response = session.post(f"{API_BASE}/query", json=query, timeout=(10, 120))
        response.raise_for_status()
        page = response.json()
        for flight in page.get("flights", []):
            start_code = str(flight.get("start_airport_ident") or "").upper()
            end_code = str(flight.get("end_airport_ident") or "").upper()
            if airport_codes.intersection((start_code, end_code)) or not (start_code or end_code):
                flights.append(flight)
                if len(flights) >= max_flights:
                    break
        cursor = page.get("cursor")
        if not cursor:
            break
        time.sleep(0.15)

    events = [event for flight in flights for event in flatten_flight(flight)]
    batch_name = f"{requested_day.isoformat()}_{airport.upper()}"
    output_dir = root / "bronze" / "adsb" / batch_name
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "flights.json").write_text(json.dumps(flights, indent=2), encoding="utf-8")
    with (output_dir / "events.jsonl").open("w", encoding="utf-8") as output:
        for event in events:
            output.write(json.dumps(event, separators=(",", ":")) + "\n")
    manifest = {
        "source": "ADSB.aero historical trajectory API",
        "airport_requested": airport.upper(),
        "airport_codes": sorted(airport_codes),
        "date_utc": requested_day.isoformat(),
        "max_flights": max_flights,
        "flights_downloaded": len(flights),
        "observations": len(events),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_response": str((output_dir / "flights.json").relative_to(root)),
        "replay_events": str((output_dir / "events.jsonl").relative_to(root)),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not events:
        raise ValueError(
            f"No ADS-B trajectory points found for {airport.upper()} on {requested_day.isoformat()}; "
            "choose a date inside the provider's available range with airport traffic."
        )
    print(f"ADS-B {requested_day.isoformat()} {airport.upper()}: {len(flights)} flights, {len(events)} observations")
    return manifest
