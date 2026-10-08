"""Create tiny PostgreSQL source tables for dbt CI without external data."""
import os

import psycopg


with psycopg.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=os.getenv("POSTGRES_PORT", "5432"),
    dbname=os.getenv("POSTGRES_DB", "flightpulse"),
    user=os.getenv("POSTGRES_USER", "flightpulse"),
    password=os.getenv("POSTGRES_PASSWORD", "flightpulse_local"),
) as connection:
    with connection.cursor() as cursor:
        cursor.execute("CREATE SCHEMA IF NOT EXISTS staging")
        cursor.execute("DROP TABLE IF EXISTS staging.bts_flights")
        cursor.execute("DROP TABLE IF EXISTS staging.adsb_observations")
        cursor.execute("""
            CREATE TABLE staging.bts_flights (
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
            INSERT INTO staging.bts_flights VALUES
            ('ci-flight-1', '2026-05-01', 19805, 'AA', '100', 12478, 'JFK', 12892, 'LAX', 800,
             -5, -10, 0, false, false, 2475, 330, null, null, null, null, null),
            ('ci-flight-2', '2026-05-01', 19805, 'AA', '101', 12892, 'LAX', 12478, 'JFK', 900,
             20, 25, 1, false, false, 2475, 340, 10, 0, 15, 0, 0)
        """)
        cursor.execute("""
            CREATE TABLE staging.adsb_observations (
                flight_id text, icao24 text, callsign text, icao_type text, operator_name text,
                start_airport_ident text, end_airport_ident text, event_ts timestamp, event_epoch bigint,
                longitude double precision, latitude double precision, altitude_ft double precision,
                track_deg double precision, ground_speed_knots double precision, vertical_rate_fpm double precision,
                indicated_airspeed_knots double precision, height_agl_ft double precision
            )
        """)
        cursor.execute("""
            INSERT INTO staging.adsb_observations VALUES
            ('ci-adsb-1', 'abc123', 'TEST123', 'B738', 'Example Air', 'KJFK', 'KLAX',
             '2026-04-30 12:00:00', 1777550400, -73.78, 40.64, 1200, 90, 180, 1000, 150, 900)
        """)
print("Created CI fixture sources in PostgreSQL staging schema")
