from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from kafka import KafkaProducer

from flightpulse.config import data_dir, spark_session
from flightpulse.processing.postgres import write_dataframe


def _event_schema():
    from pyspark.sql import types as T

    return T.StructType([
        T.StructField("flight_id", T.StringType()),
        T.StructField("icao24", T.StringType()),
        T.StructField("callsign", T.StringType()),
        T.StructField("icao_type", T.StringType()),
        T.StructField("operator_name", T.StringType()),
        T.StructField("start_airport_ident", T.StringType()),
        T.StructField("end_airport_ident", T.StringType()),
        T.StructField("event_ts", T.TimestampType()),
        T.StructField("event_epoch", T.LongType()),
        T.StructField("longitude", T.DoubleType()),
        T.StructField("latitude", T.DoubleType()),
        T.StructField("altitude_ft", T.DoubleType()),
        T.StructField("track_deg", T.DoubleType()),
        T.StructField("ground_speed_knots", T.DoubleType()),
        T.StructField("vertical_rate_fpm", T.DoubleType()),
        T.StructField("indicated_airspeed_knots", T.DoubleType()),
        T.StructField("height_agl_ft", T.DoubleType()),
    ])


def _latest_event_file(root: Path) -> Path:
    files = sorted((root / "bronze" / "adsb").glob("*/events.jsonl"))
    if not files:
        raise FileNotFoundError("No ADS-B replay file found. Run `make adsb-fetch AIRPORT=KJFK ADS_B_DATE=YYYY-MM-DD` first.")
    return files[-1]


def produce_adsb(root: Path | None = None) -> int:
    root = root or data_dir()
    event_file = _latest_event_file(root)
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = os.getenv("KAFKA_TOPIC", "adsb-observations")
    producer = KafkaProducer(
        bootstrap_servers=bootstrap.split(","),
        value_serializer=lambda value: json.dumps(value, separators=(",", ":")).encode("utf-8"),
        key_serializer=lambda value: value.encode("utf-8"),
        acks="all",
        retries=5,
    )
    count = 0
    try:
        with event_file.open(encoding="utf-8") as input_file:
            for line in input_file:
                event = json.loads(line)
                key = f"{event.get('flight_id')}:{event.get('event_epoch')}"
                producer.send(topic, key=key, value=event)
                count += 1
        producer.flush(timeout=60)
    finally:
        producer.close()
    print(f"Produced {count:,} events from {event_file} to {topic}")
    return count


def stream_adsb(root: Path | None = None) -> None:
    from pyspark.sql import functions as F

    root = root or data_dir()
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = os.getenv("KAFKA_TOPIC", "adsb-observations")
    output_path = root / "silver" / "adsb" / "observations"
    checkpoint = root / "checkpoints" / "adsb"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.mkdir(parents=True, exist_ok=True)
    spark = spark_session("FlightPulse-ADS-B-Streaming", kafka=True)
    try:
        source = (
            spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", bootstrap)
            .option("subscribe", topic)
            .option("startingOffsets", "earliest")
            .load()
        )
        parsed = source.select(F.from_json(F.col("value").cast("string"), _event_schema()).alias("event")) \
            .select("event.*")
        valid_expr = F.coalesce((
            F.col("flight_id").isNotNull()
            & F.col("event_ts").isNotNull()
            & F.col("longitude").between(-180, 180)
            & F.col("latitude").between(-90, 90)
        ), F.lit(False))
        counts = {"valid": 0, "invalid": 0}

        def write_batch(batch, batch_id: int) -> None:
            valid = batch.filter(valid_expr)
            invalid = batch.filter(~valid_expr)
            valid_count = valid.count()
            invalid_count = invalid.count()
            counts["valid"] += valid_count
            counts["invalid"] += invalid_count
            if valid_count:
                valid.write.mode("append").parquet(str(output_path))
            if invalid_count:
                invalid.write.mode("append").parquet(str(root / "quarantine" / "adsb"))

        query = (
            parsed.writeStream.foreachBatch(write_batch)
            .option("checkpointLocation", str(checkpoint))
            .trigger(availableNow=True)
            .start()
        )
        query.awaitTermination()
        quality_dir = root / "quality"
        quality_dir.mkdir(parents=True, exist_ok=True)
        (quality_dir / "adsb_quality_report.json").write_text(
            json.dumps({
                "rows_processed": counts["valid"] + counts["invalid"],
                "valid_coordinates": counts["valid"],
                "invalid_observations": counts["invalid"],
                "status": "PASS" if counts["invalid"] == 0 else "PASS_WITH_QUARANTINE",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            }, indent=2),
            encoding="utf-8",
        )
        print(f"ADS-B stream wrote Parquet to {output_path}")
    finally:
        spark.stop()


def load_adsb(root: Path | None = None) -> int:
    root = root or data_dir()
    silver_path = root / "silver" / "adsb" / "observations"
    if not silver_path.exists() or not list(silver_path.glob("*.parquet")):
        raise FileNotFoundError("No ADS-B Silver Parquet found. Run `make adsb-stream` first.")
    spark = spark_session("FlightPulse-ADS-B-Postgres", jdbc=True)
    try:
        observations = spark.read.parquet(str(silver_path)).dropDuplicates(["flight_id", "event_ts"])
        count = observations.count()
        write_dataframe(observations, "staging.adsb_observations")
        print(f"Loaded {count:,} ADS-B observations into staging.adsb_observations")
        return count
    finally:
        spark.stop()
