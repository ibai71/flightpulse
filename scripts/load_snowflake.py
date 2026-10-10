from __future__ import annotations

import os
import sys
import uuid
from getpass import getpass
from pathlib import Path

from flightpulse.config import data_dir


def _connection():
    try:
        import snowflake.connector
    except ImportError as exc:
        raise SystemExit('Snowflake packages are not installed. Run: pip install -e ".[dev,snowflake]"') from exc

    password = os.getenv("SNOWFLAKE_PASSWORD") or getpass("Snowflake password (input hidden; not saved): ")
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT", "your-org-your-account"),
        user=os.getenv("SNOWFLAKE_USER", "your-login"),
        authenticator=os.getenv("SNOWFLAKE_AUTHENTICATOR", "username_password_mfa"),
        password=password,
        role=os.getenv("SNOWFLAKE_ROLE", "FLIGHTPULSE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "FLIGHTPULSE_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "FLIGHTPULSE"),
        schema="LANDING",
    )


def _parquet_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.parquet") if path.is_file())


def _ensure_landing_objects(cursor) -> None:
    """Create the landing objects if the account setup stopped before this step."""
    statements = [
        "CREATE FILE FORMAT IF NOT EXISTS FLIGHTPULSE.LANDING.PARQUET_FORMAT "
        "TYPE=PARQUET USE_LOGICAL_TYPE=TRUE",
        "CREATE STAGE IF NOT EXISTS FLIGHTPULSE.LANDING.FLIGHTPULSE_STAGE "
        "FILE_FORMAT=(FORMAT_NAME='FLIGHTPULSE.LANDING.PARQUET_FORMAT')",
        """CREATE TABLE IF NOT EXISTS FLIGHTPULSE.LANDING.BTS_FLIGHTS (
            FLIGHT_ID VARCHAR, FLIGHT_DATE DATE, AIRLINE_ID NUMBER(38, 0),
            AIRLINE_CODE VARCHAR, FLIGHT_NUMBER VARCHAR,
            ORIGIN_AIRPORT_ID NUMBER(38, 0), ORIGIN_CODE VARCHAR,
            DESTINATION_AIRPORT_ID NUMBER(38, 0), DESTINATION_CODE VARCHAR,
            SCHEDULED_DEPARTURE_HHMM NUMBER(10, 0),
            DEPARTURE_DELAY_MINUTES FLOAT, ARRIVAL_DELAY_MINUTES FLOAT,
            ARRIVAL_DELAYED_15 NUMBER(10, 0), CANCELLED BOOLEAN, DIVERTED BOOLEAN,
            DISTANCE_MILES FLOAT, AIR_TIME_MINUTES FLOAT,
            CARRIER_DELAY_MINUTES FLOAT, WEATHER_DELAY_MINUTES FLOAT,
            NAS_DELAY_MINUTES FLOAT, SECURITY_DELAY_MINUTES FLOAT,
            LATE_AIRCRAFT_DELAY_MINUTES FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS FLIGHTPULSE.LANDING.ADSB_OBSERVATIONS (
            FLIGHT_ID VARCHAR, ICAO24 VARCHAR, CALLSIGN VARCHAR, ICAO_TYPE VARCHAR,
            OPERATOR_NAME VARCHAR, START_AIRPORT_IDENT VARCHAR, END_AIRPORT_IDENT VARCHAR,
            EVENT_TS TIMESTAMP_NTZ, EVENT_EPOCH NUMBER(38, 0), LONGITUDE FLOAT,
            LATITUDE FLOAT, ALTITUDE_FT FLOAT, TRACK_DEG FLOAT,
            GROUND_SPEED_KNOTS FLOAT, VERTICAL_RATE_FPM FLOAT,
            INDICATED_AIRSPEED_KNOTS FLOAT, HEIGHT_AGL_FT FLOAT
        )""",
        """CREATE TABLE IF NOT EXISTS FLIGHTPULSE.LANDING.LOAD_AUDIT (
            RUN_ID VARCHAR, TABLE_NAME VARCHAR, FILES_UPLOADED NUMBER(10, 0),
            ROWS_LOADED NUMBER(38, 0), LOADED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
        )""",
    ]
    for statement in statements:
        cursor.execute(statement)


def _put_files(cursor, files: list[Path], stage_prefix: str) -> None:
    cursor.execute(f"REMOVE @FLIGHTPULSE.LANDING.FLIGHTPULSE_STAGE/{stage_prefix}/")
    for path in files:
        # Snowflake PUT accepts a local file URI; quoting handles the user's Windows path.
        file_uri = ("file://" + path.resolve().as_posix()).replace("'", "''")
        cursor.execute(
            f"PUT '{file_uri}' @FLIGHTPULSE.FLIGHTPULSE.LANDING.FLIGHTPULSE_STAGE/{stage_prefix}/ "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )


def _replace_table_from_stage(cursor, table: str, stage_prefix: str, files: list[Path]) -> int:
    if not files:
        return 0
    load_table = f"{table}_LOAD"
    cursor.execute(f"CREATE OR REPLACE TABLE FLIGHTPULSE.LANDING.{load_table} LIKE FLIGHTPULSE.LANDING.{table}")
    cursor.execute(
        f"COPY INTO FLIGHTPULSE.LANDING.{load_table} "
        f"FROM @FLIGHTPULSE.LANDING.FLIGHTPULSE_STAGE/{stage_prefix}/ "
        "FILE_FORMAT=(FORMAT_NAME='FLIGHTPULSE.LANDING.PARQUET_FORMAT') "
        "MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE FORCE=TRUE"
    )
    cursor.execute(f"SELECT COUNT(*) FROM FLIGHTPULSE.LANDING.{load_table}")
    row_count = int(cursor.fetchone()[0])
    if row_count == 0:
        cursor.execute(f"DROP TABLE IF EXISTS FLIGHTPULSE.LANDING.{load_table}")
        raise RuntimeError(f"Snowflake loaded zero rows from the {table} Parquet files; existing data was preserved.")
    cursor.execute(
        f"CREATE OR REPLACE TABLE FLIGHTPULSE.LANDING.{table} "
        f"AS SELECT * FROM FLIGHTPULSE.LANDING.{load_table}"
    )
    cursor.execute(f"DROP TABLE FLIGHTPULSE.LANDING.{load_table}")
    return row_count


def main() -> int:
    root = data_dir()
    bts_dir = root / "silver" / "bts"
    adsb_dir = root / "silver" / "adsb" / "observations"
    bts_files = _parquet_files(bts_dir) if bts_dir.exists() else []
    adsb_files = _parquet_files(adsb_dir) if adsb_dir.exists() else []
    if not bts_files:
        raise SystemExit(f"No BTS Silver Parquet found under {bts_dir}. Run the local BTS pipeline first.")

    connection = _connection()
    try:
        with connection.cursor() as cursor:
            _ensure_landing_objects(cursor)
            _put_files(cursor, bts_files, "bts")
            bts_count = _replace_table_from_stage(cursor, "BTS_FLIGHTS", "bts", bts_files)
            cursor.execute(
                "INSERT INTO FLIGHTPULSE.LANDING.LOAD_AUDIT (RUN_ID, TABLE_NAME, FILES_UPLOADED, ROWS_LOADED) "
                "VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), "BTS_FLIGHTS", len(bts_files), bts_count),
            )
            cursor.execute("REMOVE @FLIGHTPULSE.LANDING.FLIGHTPULSE_STAGE/bts/")
            print(f"Loaded {bts_count:,} BTS flight records into FLIGHTPULSE.LANDING.BTS_FLIGHTS")
            if adsb_files:
                _put_files(cursor, adsb_files, "adsb")
                adsb_count = _replace_table_from_stage(cursor, "ADSB_OBSERVATIONS", "adsb", adsb_files)
                cursor.execute(
                    "INSERT INTO FLIGHTPULSE.LANDING.LOAD_AUDIT (RUN_ID, TABLE_NAME, FILES_UPLOADED, ROWS_LOADED) "
                    "VALUES (%s, %s, %s, %s)",
                    (str(uuid.uuid4()), "ADSB_OBSERVATIONS", len(adsb_files), adsb_count),
                )
                cursor.execute("REMOVE @FLIGHTPULSE.LANDING.FLIGHTPULSE_STAGE/adsb/")
                print(f"Loaded {adsb_count:,} ADS-B observations into FLIGHTPULSE.LANDING.ADSB_OBSERVATIONS")
            else:
                print("No ADS-B Silver files found; existing Snowflake ADS-B landing table was left unchanged.")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
