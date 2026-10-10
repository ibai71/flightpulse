"""Create a small deterministic synthetic snapshot for the public dashboard preview."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


OUT = Path(__file__).resolve().parents[1] / "dashboard" / "data" / "demo"
DAYS = [datetime(2026, 5, 1) + timedelta(days=i) for i in range(92)]
AIRPORTS = [("JFK", 0), ("LAX", 1), ("ORD", 2), ("ATL", 3), ("DFW", 4), ("SEA", 5), ("MIA", 6), ("BOS", 7)]
AIRLINES = ["AA", "DL", "UA", "WN", "B6"]
AIRLINE_NAMES = {"AA": "American Airlines", "DL": "Delta Air Lines", "UA": "United Airlines", "WN": "Southwest Airlines", "B6": "JetBlue Airways"}
AIRPORT_NAMES = {"JFK": "New York, NY", "LAX": "Los Angeles, CA", "ORD": "Chicago, IL", "ATL": "Atlanta, GA", "DFW": "Dallas/Fort Worth, TX", "SEA": "Seattle, WA", "MIA": "Miami, FL", "BOS": "Boston, MA"}
CAUSES = ["carrier", "weather", "nas", "security", "late_aircraft"]


def save(name: str, rows: list[dict]) -> None:
    path = OUT / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} synthetic rows: {path}")


def main() -> None:
    airport_rows = []
    airport_volumes = [540, 495, 450, 420, 390, 330, 310, 285]
    for day_index, day in enumerate(DAYS):
        for airport_index, ((code, _), volume) in enumerate(zip(AIRPORTS, airport_volumes)):
            for role in ("origin", "destination"):
                scheduled = int(volume * (0.82 + 0.30 * math.sin(day_index / 9 + airport_index)) * (1 if role == "origin" else 0.96))
                cancel = round(scheduled * (0.012 + 0.01 * (airport_index in (2, 3))))
                divert = round(scheduled * 0.003)
                eligible = scheduled - cancel - divert
                otp = max(0.68, min(0.96, 0.91 - 0.018 * airport_index + 0.025 * math.sin(day_index / 7 + airport_index)))
                on_time = round(eligible * otp)
                airport_rows.append({"flight_date": day.date().isoformat(), "airport_id": 10000 + airport_index, "airport_code": code, "airport_role": role, "scheduled_flights": scheduled, "cancelled_flights": cancel, "diverted_flights": divert, "average_delay_minutes": round(7 + airport_index * 2.1 + 4 * math.sin(day_index / 8 + airport_index), 2), "eligible_flights": eligible, "on_time_flights": on_time, "on_time_rate": round(on_time / eligible, 5) if eligible else "", "cancellation_rate": round(cancel / scheduled, 5) if scheduled else "", "diversion_rate": round(divert / scheduled, 5) if scheduled else ""})
    save("airport_daily_performance", airport_rows)

    airline_rows = []
    sizes = {"AA": 920, "DL": 840, "UA": 790, "WN": 740, "B6": 300}
    otp_base = {"AA": .865, "DL": .902, "UA": .882, "WN": .891, "B6": .844}
    for day_index, day in enumerate(DAYS):
        for airline in AIRLINES:
            scheduled = int(sizes[airline] * (0.93 + .12 * math.sin(day_index / 10 + len(airline))))
            cancelled = round(scheduled * (.012 + .008 * (day_index % 21 == 0)))
            diverted = round(scheduled * .003)
            eligible = scheduled - cancelled - diverted
            otp = otp_base[airline] + .025 * math.sin(day_index / 8 + len(airline))
            ontime = round(eligible * otp)
            airline_rows.append({"flight_date": day.date().isoformat(), "airline_id": 19000 + AIRLINES.index(airline), "airline_code": airline, "scheduled_flights": scheduled, "cancelled_flights": cancelled, "diverted_flights": diverted, "average_arrival_delay_minutes": round(14 - otp * 9 + 4 * math.sin(day_index / 6), 2), "eligible_arrivals": eligible, "on_time_arrivals": ontime, "cancellation_rate": round(cancelled / scheduled, 5), "diversion_rate": round(diverted / scheduled, 5), "on_time_rate": round(ontime / eligible, 5)})
    save("airline_daily_performance", airline_rows)

    cause_rows = []
    for day_index, day in enumerate(DAYS):
        for airline in AIRLINES:
            for cause_index, cause in enumerate(CAUSES):
                total = int((cause_index + 2) * (45 + 12 * math.sin(day_index / 5 + cause_index)) * (1 + AIRLINES.index(airline) * .12))
                cause_rows.append({"flight_date": day.date().isoformat(), "airline_id": 19000 + AIRLINES.index(airline), "airline_code": airline, "origin_airport_code": AIRPORTS[(day_index + cause_index) % 8][0], "destination_airport_code": AIRPORTS[(day_index + cause_index + 2) % 8][0], "delay_cause": cause, "flights_with_cause": int(total / (cause_index + 3)), "total_delay_minutes": total, "average_delay_minutes": round(total / max(int(total / (cause_index + 3)), 1), 2)})
    save("delay_causes", cause_rows)

    route_rows = []
    for origin, destination in [("JFK", "LAX"), ("LAX", "JFK"), ("ORD", "LAX"), ("ATL", "JFK"), ("DFW", "SEA"), ("BOS", "MIA"), ("SEA", "SFO"), ("MIA", "ATL")]:
        idx = len(route_rows)
        flights = 1800 - idx * 140
        eligible = int(flights * .96)
        otp = .92 - idx * .022
        route_rows.append({"origin_airport_id": 10000 + idx, "origin_airport_code": origin, "destination_airport_id": 11000 + idx, "destination_airport_code": destination, "scheduled_flights": flights, "average_arrival_delay_minutes": round(8 + idx * 2.6, 2), "eligible_arrivals": eligible, "on_time_arrivals": round(eligible * otp), "cancellation_rate": .018 + idx * .002, "diversion_rate": .003, "on_time_rate": round(otp, 5)})
    save("route_performance", route_rows)

    adsb_rows = []
    airport_coords = {"KJFK": (-73.7781, 40.6413), "KLAX": (-118.4085, 33.9416), "KORD": (-87.9073, 41.9742), "KATL": (-84.4277, 33.6407), "KDFW": (-97.0403, 32.8998)}
    pairs = [("KJFK", "KLAX"), ("KJFK", "KORD"), ("KATL", "KJFK"), ("KDFW", "KLAX"), ("KORD", "KATL")]
    base_ts = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
    for flight_idx, (start, end) in enumerate(pairs):
        lon1, lat1 = airport_coords[start]
        lon2, lat2 = airport_coords[end]
        for point in range(30):
            fraction = point / 29
            adsb_rows.append({"flight_id": f"demo-adsb-{flight_idx + 1}", "icao24": f"a{flight_idx:05x}", "callsign": f"FP{100 + flight_idx}", "icao_type": ["B738", "A320", "B739", "A321", "B752"][flight_idx], "operator_name": AIRLINES[flight_idx], "start_airport_ident": start, "end_airport_ident": end, "event_ts": (base_ts + timedelta(minutes=flight_idx * 8 + point * 5)).isoformat(), "event_epoch": int((base_ts + timedelta(minutes=flight_idx * 8 + point * 5)).timestamp()), "longitude": round(lon1 + (lon2 - lon1) * fraction + math.sin(fraction * math.pi) * 1.2, 5), "latitude": round(lat1 + (lat2 - lat1) * fraction + math.sin(fraction * math.pi) * 1.5, 5), "altitude_ft": int(900 + 35000 * min(1, fraction * 4, (1-fraction) * 4)), "track_deg": round((math.degrees(math.atan2(lon2-lon1, lat2-lat1)) + 360) % 360, 1), "ground_speed_knots": int(150 + 300 * min(1, fraction * 4, (1-fraction) * 4)), "vertical_rate_fpm": 0, "indicated_airspeed_knots": 260, "height_agl_ft": ""})
    save("fact_adsb_observations", adsb_rows)
    save("airport_labels", [{"airport_code": code, "airport_name": name} for code, name in AIRPORT_NAMES.items()])
    save("airline_labels", [{"airline_code": code, "airline_name": name} for code, name in AIRLINE_NAMES.items()])
    aircraft_names = {"B738": "Boeing 737-800", "A320": "Airbus A320", "B739": "Boeing 737-900", "A321": "Airbus A321", "B752": "Boeing 757-200"}
    save("aircraft_labels", [{"icao_type": code, "aircraft_name": name} for code, name in aircraft_names.items()])
    (OUT / "dataset_info.json").write_text(json.dumps({"data_type": "synthetic_preview"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
