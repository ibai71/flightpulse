import pytest
import sys
from pathlib import Path

if sys.platform == "win32":
    pytest.skip("PySpark batch tests run in the project's Linux/WSL2 environment", allow_module_level=True)

pyspark = pytest.importorskip("pyspark")

from flightpulse.processing.bts import normalize_bts, quality_partition


@pytest.fixture(scope="module")
def spark():
    session = (
        pyspark.sql.SparkSession.builder.master("local[1]")
        .appName("flightpulse-tests")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()


def test_transform_deduplicates_and_keeps_early_arrivals(spark):
    path = Path(__file__).parent / "fixtures" / "bts_sample.csv"
    raw = spark.read.option("header", True).option("inferSchema", False).csv(str(path))
    typed = normalize_bts(raw)
    clean, rejected, report = quality_partition(typed)
    result = clean.collect()
    assert len(result) == 2
    assert any(row.arrival_delay_minutes == -10 for row in result)
    assert all(row.flight_date.isoformat() == "2026-05-01" for row in result)
    assert rejected.count() == 1
    assert report["duplicates_removed"] == 1
    assert report["invalid_airports"] == 1


def test_transform_quarantines_invalid_airport_codes(spark):
    row = (
        "2026-05-01", "19805", "AA", "100", "12478", "J@K", "12892", "LAX",
        "800", "0", "0", "0", "0", "0", "2475", "330", None, None, None, None, None,
    )
    columns = [
        "FlightDate", "DOT_ID_Reporting_Airline", "Reporting_Airline", "Flight_Number_Reporting_Airline",
        "OriginAirportID", "Origin", "DestAirportID", "Dest", "CRSDepTime", "DepDelayMinutes",
        "ArrDelayMinutes", "ArrDel15", "Cancelled", "Diverted", "Distance", "AirTime", "CarrierDelay",
        "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
    ]
    schema = pyspark.sql.types.StructType([
        pyspark.sql.types.StructField(name, pyspark.sql.types.StringType(), nullable=True)
        for name in columns
    ])
    clean, rejected, report = quality_partition(normalize_bts(spark.createDataFrame([row], schema)))
    assert clean.count() == 0
    assert rejected.count() == 1
    assert report["invalid_airports"] == 1
