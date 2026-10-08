from __future__ import annotations

import os
from typing import TYPE_CHECKING

import psycopg
from psycopg import sql

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

from flightpulse.config import postgres_connection


def ensure_schema(schema: str = "staging") -> None:
    config = postgres_connection()
    with psycopg.connect(
        host=config["host"], port=config["port"], dbname=config["dbname"],
        user=config["user"], password=config["password"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


def ensure_source_tables() -> None:
    """Create empty ingestion relations so dbt can build either pipeline independently."""
    config = postgres_connection()
    with psycopg.connect(
        host=config["host"], port=config["port"], dbname=config["dbname"],
        user=config["user"], password=config["password"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS staging")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staging.bts_flights (
                    flight_id text, flight_date date, airline_id bigint, airline_code text, flight_number text,
                    origin_airport_id bigint, origin_code text, destination_airport_id bigint, destination_code text,
                    scheduled_departure_hhmm integer, departure_delay_minutes double precision,
                    arrival_delay_minutes double precision, arrival_delayed_15 integer, cancelled boolean,
                    diverted boolean, distance_miles double precision, air_time_minutes double precision,
                    carrier_delay_minutes double precision, weather_delay_minutes double precision,
                    nas_delay_minutes double precision, security_delay_minutes double precision,
                    late_aircraft_delay_minutes double precision
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS staging.adsb_observations (
                    flight_id text, icao24 text, callsign text, icao_type text, operator_name text,
                    start_airport_ident text, end_airport_ident text, event_ts timestamp, event_epoch bigint,
                    longitude double precision, latitude double precision, altitude_ft double precision,
                    track_deg double precision, ground_speed_knots double precision, vertical_rate_fpm double precision,
                    indicated_airspeed_knots double precision, height_agl_ft double precision
                )
            """)


def write_dataframe(df: "DataFrame", table: str, mode: str = "overwrite") -> None:
    schema, table_name = table.split(".", 1)
    ensure_schema(schema)
    config = postgres_connection()
    write_mode = mode
    if mode == "overwrite":
        with psycopg.connect(
            host=config["host"], port=config["port"], dbname=config["dbname"],
            user=config["user"], password=config["password"],
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass(%s)", (f"{schema}.{table_name}",))
                if cursor.fetchone()[0] is not None:
                    cursor.execute(
                        sql.SQL("TRUNCATE TABLE {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(table_name)
                        )
                    )
                    write_mode = "append"
    properties = {
        "user": config["user"],
        "password": config["password"],
        "driver": os.getenv("POSTGRES_JDBC_DRIVER", "org.postgresql.Driver"),
    }
    df.write.jdbc(url=config["jdbc_url"], table=table, mode=write_mode, properties=properties)
