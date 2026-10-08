from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import DataFrame, functions as F

from flightpulse.config import data_dir, spark_session
from flightpulse.ingestion.bts import month_sequence
from flightpulse.processing.postgres import write_dataframe


REQUIRED_COLUMNS = [
    "FlightDate", "DOT_ID_Reporting_Airline", "Flight_Number_Reporting_Airline",
    "OriginAirportID", "DestAirportID", "CRSDepTime", "Origin", "Dest",
]
OPTIONAL_COLUMNS = [
    "Reporting_Airline", "DepDelayMinutes", "ArrDelayMinutes", "ArrDel15", "Cancelled",
    "Diverted", "Distance", "AirTime", "CarrierDelay", "WeatherDelay", "NASDelay",
    "SecurityDelay", "LateAircraftDelay",
]


def _try_cast(column: str, data_type: str):
    return F.expr(f"try_cast(`{column}` AS {data_type})")


def normalize_bts(raw: DataFrame) -> DataFrame:
    """Select and type the BTS fields used by FlightPulse."""
    renamed = raw.toDF(*[name.lstrip("\ufeff").strip() for name in raw.columns])
    missing = sorted(set(REQUIRED_COLUMNS) - set(renamed.columns))
    if missing:
        raise ValueError(f"BTS source is missing required columns: {', '.join(missing)}")
    frame = renamed
    for name in OPTIONAL_COLUMNS:
        if name not in frame.columns:
            frame = frame.withColumn(name, F.lit(None).cast("string"))

    flight_date = F.coalesce(
        F.to_date(F.expr("try_to_timestamp(`FlightDate`, 'yyyy-MM-dd')")),
        F.to_date(F.expr("try_to_timestamp(`FlightDate`, 'yyyyMMdd')")),
    )
    normalized = frame.select(
        flight_date.alias("flight_date"),
        _try_cast("DOT_ID_Reporting_Airline", "BIGINT").alias("airline_id"),
        F.trim(F.col("Reporting_Airline")).alias("airline_code"),
        F.trim(F.col("Flight_Number_Reporting_Airline")).alias("flight_number"),
        _try_cast("OriginAirportID", "BIGINT").alias("origin_airport_id"),
        F.upper(F.trim(F.col("Origin"))).alias("origin_code"),
        _try_cast("DestAirportID", "BIGINT").alias("destination_airport_id"),
        F.upper(F.trim(F.col("Dest"))).alias("destination_code"),
        _try_cast("CRSDepTime", "INT").alias("scheduled_departure_hhmm"),
        _try_cast("DepDelayMinutes", "DOUBLE").alias("departure_delay_minutes"),
        _try_cast("ArrDelayMinutes", "DOUBLE").alias("arrival_delay_minutes"),
        _try_cast("ArrDel15", "INT").alias("arrival_delayed_15"),
        _try_cast("Cancelled", "DOUBLE").alias("cancelled_raw"),
        _try_cast("Diverted", "DOUBLE").alias("diverted_raw"),
        _try_cast("Distance", "DOUBLE").alias("distance_miles"),
        _try_cast("AirTime", "DOUBLE").alias("air_time_minutes"),
        _try_cast("CarrierDelay", "DOUBLE").alias("carrier_delay_minutes"),
        _try_cast("WeatherDelay", "DOUBLE").alias("weather_delay_minutes"),
        _try_cast("NASDelay", "DOUBLE").alias("nas_delay_minutes"),
        _try_cast("SecurityDelay", "DOUBLE").alias("security_delay_minutes"),
        _try_cast("LateAircraftDelay", "DOUBLE").alias("late_aircraft_delay_minutes"),
    ).withColumn("cancelled", F.col("cancelled_raw") > 0) \
     .withColumn("diverted", F.col("diverted_raw") > 0) \
     .drop("cancelled_raw", "diverted_raw")

    key_values = F.concat_ws(
        "|",
        F.date_format("flight_date", "yyyy-MM-dd"),
        F.col("airline_id").cast("string"),
        F.col("flight_number"),
        F.col("origin_airport_id").cast("string"),
        F.col("destination_airport_id").cast("string"),
        F.col("scheduled_departure_hhmm").cast("string"),
    )
    return normalized.withColumn("flight_id", F.sha2(key_values, 256))


def quality_partition(frame: DataFrame) -> tuple[DataFrame, DataFrame, dict[str, int | str]]:
    key_valid = F.coalesce((
        F.col("flight_date").isNotNull()
        & (F.col("airline_id") > 0)
        & F.col("flight_number").isNotNull()
        & (F.length(F.col("flight_number")) > 0)
        & (F.col("origin_airport_id") > 0)
        & (F.col("destination_airport_id") > 0)
        & F.col("scheduled_departure_hhmm").isNotNull()
    ), F.lit(False))
    airport_valid = F.coalesce(
        F.col("origin_code").rlike("^[A-Z0-9]{3}$") & F.col("destination_code").rlike("^[A-Z0-9]{3}$"),
        F.lit(False),
    )
    distance_valid = F.coalesce(F.col("distance_miles").isNull() | (F.col("distance_miles") >= 0), F.lit(False))
    valid_expr = key_valid & airport_valid & distance_valid

    raw_count = frame.count()
    invalid_keys = frame.filter(~key_valid).count()
    invalid_airports = frame.filter(key_valid & ~airport_valid).count()
    invalid_distance = frame.filter(key_valid & airport_valid & ~distance_valid).count()
    rejected = frame.filter(~valid_expr)
    good = frame.filter(valid_expr)
    before_dedupe = good.count()
    deduped = good.dropDuplicates(["flight_id"])
    duplicate_count = before_dedupe - deduped.count()
    report: dict[str, int | str] = {
        "rows_processed": raw_count,
        "duplicates_removed": duplicate_count,
        "missing_or_invalid_critical_ids": invalid_keys,
        "invalid_airports": invalid_airports,
        "invalid_distance": invalid_distance,
        "rows_quarantined": raw_count - before_dedupe,
        "rows_silver": before_dedupe - duplicate_count,
        "status": "PASS" if invalid_keys == 0 and invalid_airports == 0 and invalid_distance == 0 else "PASS_WITH_QUARANTINE",
    }
    return deduped, rejected, report


def _write_report(report: dict[str, int | str], root: Path) -> None:
    output = root / "quality" / "bts_quality_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")


def build_bts(
    root: Path | None = None,
    load_postgres: bool = True,
    start_month: str = "2026-05",
    end_month: str = "2026-07",
) -> dict[str, int | str]:
    root = root or data_dir()
    parquet_root = root / "bronze" / "bts" / "parquet"
    months = month_sequence(start_month, end_month)
    inputs = [parquet_root / f"year={year}" / f"month={month:02d}" for year, month in months]
    missing = [path for path in inputs if not path.exists() or not list(path.glob("*.parquet"))]
    if missing:
        missing_months = [f"{path.parent.name[5:]}-{path.name[6:]}" for path in missing]
        raise FileNotFoundError(
            "Missing BTS Bronze months: " + ", ".join(missing_months) + ". Run `make bts-ingest` for this range first."
        )

    spark = spark_session("FlightPulse-BTS-Silver", jdbc=load_postgres)
    try:
        raw = spark.read.option("basePath", str(parquet_root)).parquet(*[str(path) for path in inputs])
        typed = normalize_bts(raw)
        silver, rejected, report = quality_partition(typed)
        silver_path = root / "silver" / "bts"
        quarantine_path = root / "quarantine" / "bts"
        silver.write.mode("overwrite").parquet(str(silver_path))
        rejected.write.mode("overwrite").parquet(str(quarantine_path))
        if load_postgres:
            write_dataframe(silver, "staging.bts_flights")
        report["period_start_month"] = start_month
        report["period_end_month"] = end_month
        _write_report(report, root)
        return report
    finally:
        spark.stop()
