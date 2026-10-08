# Architecture

FlightPulse has two independent pipelines that share PostgreSQL/dbt serving models.

## BTS batch

1. `flightpulse ingest-bts` downloads one official monthly ZIP per requested month, retries transient HTTP errors, checks that the response is a ZIP, and records a SHA-256 manifest.
2. PySpark reads the source CSV with a header, keeps the source fields in Bronze Parquet, and does not overwrite the original archive.
3. `flightpulse build-bts` normalizes the fields used by analytics, quarantines invalid critical identifiers/airport codes/distances, deduplicates on a composite flight identity, writes Silver Parquet, and loads the result into `staging.bts_flights` through JDBC.
4. dbt creates dimensions, the flight fact, and aggregate models in PostgreSQL `analytics`.

The flight identity is a SHA-256 of flight date, DOT reporting-carrier ID, reported flight number, origin/destination airport IDs, and scheduled departure HHMM. Nulls are not replaced with zeros in delay measurements.

## ADS-B bounded replay

1. `flightpulse fetch-adsb` resolves the airport and its published aerodrome geometry, then queries one UTC day with an endpoint-within filter and a maximum flight count. If no aerodrome boundary is published, it uses a 3 km circle around the airport.
2. It stores the API response and emits one JSON event per path point to a local JSON Lines replay file.
3. `flightpulse produce-adsb` publishes the events to Kafka. `flightpulse stream-adsb` uses Spark Structured Streaming's available-now trigger, validates coordinates, writes valid observations to Silver Parquet, and quarantines invalid observations. A checkpoint records consumed Kafka offsets.
4. `flightpulse load-adsb` writes the deduplicated Silver observations to `staging.adsb_observations`; dbt builds `analytics.fact_adsb_observations`.

ADS-B is intentionally not entity-matched to BTS. The streaming checkpoint persists under `data/checkpoints`; deleting it replays the Kafka topic from its earliest retained offset.

## Local services

Docker Compose starts a single-node Kafka 4.1 KRaft broker and PostgreSQL 17. The Windows PowerShell runner launches FlightPulse in a Python 3.12 container with Java 17, where PySpark runs with `local[*]`. The first Spark jobs that need JDBC/Kafka may download the connector JARs from Maven Central. Direct local execution in WSL2 is also supported.

## Repository paths

- `src/flightpulse/ingestion`: BTS and ADS-B acquisition.
- `src/flightpulse/processing`: BTS transformations, JDBC loading, quality report.
- `src/flightpulse/streaming`: Kafka producer and Spark streaming consumer.
- `dbt/models`: source declarations, staging views, and analytics models.
- `tests/fixtures`: tiny hand-authored inputs for deterministic tests.
- `data/`: downloaded/generated data; ignored by Git.
