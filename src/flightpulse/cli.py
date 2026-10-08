from __future__ import annotations

import argparse
import os
import subprocess
import sys

from flightpulse.config import PROJECT_ROOT
from flightpulse.ingestion.adsb import fetch_adsb
from flightpulse.ingestion.bts import ingest_range


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flightpulse", description="Run local FlightPulse data pipelines")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest-bts", help="Download BTS monthly ZIPs and create Bronze Parquet")
    ingest.add_argument("--start-month", default="2026-05", help="First month, inclusive (YYYY-MM)")
    ingest.add_argument("--end-month", default="2026-07", help="Last month, inclusive (YYYY-MM)")

    build = commands.add_parser("build-bts", help="Create BTS Silver Parquet, load PostgreSQL staging, and report quality")
    build.add_argument("--start-month", default="2026-05", help="First ingested month to process (YYYY-MM)")
    build.add_argument("--end-month", default="2026-07", help="Last ingested month to process (YYYY-MM)")

    fetch = commands.add_parser("fetch-adsb", help="Fetch a bounded ADS-B airport sample")
    fetch.add_argument("--airport", default=os.getenv("ADS_B_AIRPORT", "KJFK"))
    fetch.add_argument("--date", default=os.getenv("ADS_B_DATE") or None, help="UTC date (YYYY-MM-DD)")
    fetch.add_argument("--max-flights", type=int, default=int(os.getenv("ADS_B_MAX_FLIGHTS", "40")))

    commands.add_parser("produce-adsb", help="Publish local ADS-B observations to Kafka")
    commands.add_parser("stream-adsb", help="Process available Kafka events into Silver Parquet")
    commands.add_parser("load-adsb", help="Load ADS-B Silver Parquet into PostgreSQL staging")
    commands.add_parser("dbt-run", help="Build Gold models using dbt")
    commands.add_parser("dbt-test", help="Run dbt data tests")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest-bts":
        if sys.platform == "win32":
            raise SystemExit("BTS ingest uses PySpark; run it from WSL2 with the Linux virtual environment.")
        ingest_range(args.start_month, args.end_month)
    elif args.command == "build-bts":
        if sys.platform == "win32":
            raise SystemExit("BTS processing uses PySpark; run it from WSL2 with the Linux virtual environment.")
        from flightpulse.processing.bts import build_bts

        report = build_bts(start_month=args.start_month, end_month=args.end_month)
        print(f"BTS quality: {report['status']} ({report['rows_silver']:,} rows in Silver)")
    elif args.command == "fetch-adsb":
        if not args.date:
            raise SystemExit("Choose an archive day with `make adsb-fetch AIRPORT=KJFK ADS_B_DATE=YYYY-MM-DD`.")
        fetch_adsb(args.airport, args.date, max_flights=args.max_flights)
    elif args.command == "produce-adsb":
        from flightpulse.streaming.adsb import produce_adsb

        produce_adsb()
    elif args.command == "stream-adsb":
        if sys.platform == "win32":
            raise SystemExit("ADS-B streaming uses PySpark; run it from WSL2 with the Linux virtual environment.")
        from flightpulse.streaming.adsb import stream_adsb

        stream_adsb()
    elif args.command == "load-adsb":
        if sys.platform == "win32":
            raise SystemExit("ADS-B loading uses PySpark; run it from WSL2 with the Linux virtual environment.")
        from flightpulse.streaming.adsb import load_adsb

        load_adsb()
    elif args.command in ("dbt-run", "dbt-test"):
        from flightpulse.processing.postgres import ensure_source_tables

        ensure_source_tables()
        action = "run" if args.command == "dbt-run" else "test"
        process = subprocess.run(
            [sys.executable, "-m", "dbt.cli.main", action, "--project-dir", str(PROJECT_ROOT / "dbt"), "--profiles-dir", str(PROJECT_ROOT / "dbt")],
            cwd=PROJECT_ROOT,
            check=False,
        )
        return process.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
