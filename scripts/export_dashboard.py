"""Export public, aggregated dashboard relations from FlightPulse analytics."""
from __future__ import annotations

import argparse
import csv
import json
import os
import zipfile
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "airport_daily_performance": "airport_daily_performance",
    "airline_daily_performance": "airline_daily_performance",
    "delay_causes": "delay_causes",
    "route_performance": "route_performance",
    "fact_adsb_observations": "fact_adsb_observations",
}
TABLE_QUERIES = {
    "delay_causes": """
        SELECT flight_date, airline_id, airline_code, delay_cause,
               sum(flights_with_cause)::bigint AS flights_with_cause,
               sum(total_delay_minutes) AS total_delay_minutes,
               sum(total_delay_minutes) / nullif(sum(flights_with_cause), 0) AS average_delay_minutes
        FROM analytics.delay_causes
        GROUP BY 1, 2, 3, 4
    """,
}
AIRLINE_NAMES = {
    "AA": "American Airlines", "AS": "Alaska Airlines", "B6": "JetBlue Airways",
    "DL": "Delta Air Lines", "F9": "Frontier Airlines", "G4": "Allegiant Air",
    "MQ": "Envoy Air", "NK": "Spirit Airlines", "OH": "PSA Airlines",
    "OO": "SkyWest Airlines", "UA": "United Airlines", "WN": "Southwest Airlines",
    "YX": "Republic Airways",
}


def write_lookup(output: Path, name: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    with (output / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def airport_lookup() -> list[dict[str, str]]:
    """Use human-readable city labels carried in the downloaded official BTS ZIPs."""
    names: dict[str, str] = {}
    archive = ROOT / "data" / "bronze" / "bts" / "archive"
    for source in sorted(archive.glob("year=*/month=*/source.zip")):
        with zipfile.ZipFile(source) as bundle:
            csv_name = next((name for name in bundle.namelist() if name.lower().endswith(".csv")), None)
            if csv_name is None:
                continue
            with bundle.open(csv_name) as binary:
                reader = csv.DictReader((line.decode("utf-8-sig") for line in binary))
                for row in reader:
                    for code_key, city_key in (("Origin", "OriginCityName"), ("Dest", "DestCityName")):
                        code, city = row.get(code_key, "").strip(), row.get(city_key, "").strip()
                        if code and city:
                            names[code] = city
    return [{"airport_code": code, "airport_name": names[code]} for code in sorted(names)]


def aircraft_lookup() -> list[dict[str, str]]:
    """Use ADSB.aero's model descriptions where present instead of exposing ICAO type codes."""
    models: dict[str, str] = {}
    for source in sorted((ROOT / "data" / "bronze" / "adsb").glob("*/flights.json")):
        try:
            flights = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for flight in flights:
            code, model = flight.get("icao_type"), flight.get("model")
            if code and model:
                models[code] = model.title()
    return [{"icao_type": code, "aircraft_name": models[code]} for code in sorted(models)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dashboard" / "data" / "export")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    load_dotenv(ROOT / ".env")
    conninfo = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB", "flightpulse"),
        "user": os.getenv("POSTGRES_USER", "flightpulse"),
        "password": os.getenv("POSTGRES_PASSWORD", "flightpulse_local"),
    }
    with psycopg.connect(**conninfo) as connection:
        with connection.cursor() as cursor:
            for filename, relation in TABLES.items():
                select = sql.SQL(TABLE_QUERIES[filename]) if filename in TABLE_QUERIES else sql.SQL("SELECT * FROM analytics.{}").format(sql.Identifier(relation))
                query = sql.SQL("COPY ({}) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)").format(select)
                with (args.output / f"{filename}.csv").open("w", encoding="utf-8", newline="") as output:
                    with cursor.copy(query) as copy:
                        for chunk in copy:
                            output.write(chunk if isinstance(chunk, str) else bytes(chunk).decode("utf-8"))
                print(f"Exported analytics.{relation} -> {args.output / (filename + '.csv')}")

            cursor.execute("SELECT min(flight_date), max(flight_date), count(*) FROM analytics.fact_flights")
            min_date, max_date, flight_count = cursor.fetchone()
            cursor.execute("SELECT count(*) FROM analytics.fact_adsb_observations")
            adsb_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(DISTINCT airport_id) FROM analytics.dim_airport")
            airport_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(DISTINCT airline_id) FROM analytics.dim_airline")
            airline_count = cursor.fetchone()[0]

    adsb_manifest = {}
    manifests = sorted((ROOT / "data" / "bronze" / "adsb").glob("*/manifest.json"))
    if manifests:
        adsb_manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))

    write_lookup(args.output, "airport_labels", airport_lookup())
    write_lookup(args.output, "airline_labels", [
        {"airline_code": code, "airline_name": name} for code, name in sorted(AIRLINE_NAMES.items())
    ])
    write_lookup(args.output, "aircraft_labels", aircraft_lookup())
    metadata = {
        "data_type": "public_source_snapshot",
        "flight_date_start": min_date.isoformat() if min_date else None,
        "flight_date_end": max_date.isoformat() if max_date else None,
        "flight_rows": flight_count,
        "adsb_observations": adsb_count,
        "airports": airport_count,
        "airlines": airline_count,
        "adsb_date_utc": adsb_manifest.get("date_utc"),
        "adsb_airport_requested": adsb_manifest.get("airport_requested"),
        "adsb_flights_downloaded": adsb_manifest.get("flights_downloaded"),
        "sources": ["BTS TranStats On-Time Performance", "ADSB.aero historical trajectories"],
        "adsb_note": "Bounded public trajectory sample. Kept separate from BTS; no flight matching is performed.",
    }
    (args.output / "dataset_info.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Snapshot metadata: {metadata}")


if __name__ == "__main__":
    main()
