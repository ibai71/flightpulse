# FlightPulse | Aviation Data Engineering

**An end-to-end data platform for analyzing flight punctuality, delays, cancellations, and aircraft trajectories.**

[**Live dashboard**](https://flightpulse-jvqs3gi87gnh4pbu2f2vtj.streamlit.app/) · [Architecture](docs/architecture.md) · [Data dictionary](docs/data_dictionary.md) · [Metrics](docs/metrics.md) · [ML study](docs/ml.md)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![PySpark](https://img.shields.io/badge/PySpark-4.1-E25A1C?logo=apachespark&logoColor=white)
![Kafka](https://img.shields.io/badge/Kafka-4.1-231F20?logo=apachekafka&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)
![dbt](https://img.shields.io/badge/dbt-Postgres%20%7C%20Snowflake-FF694B?logo=dbt&logoColor=white)
![CI](https://github.com/ibai71/flightpulse/actions/workflows/ci.yml/badge.svg)

## What it does

FlightPulse turns two aviation datasets into repeatable data pipelines and analytics:

- **Batch:** monthly U.S. flight-performance reports from BTS TranStats are ingested, validated, deduplicated, and transformed with PySpark.
- **Streaming:** a bounded historical ADS-B sample is replayed through Kafka and processed with Spark Structured Streaming, including checkpointing and invalid-record quarantine.
- **Analytics:** dbt builds dimensions, facts, and performance marts in PostgreSQL. An optional Snowflake target uses the same analytical model set.
- **ML:** a calibrated classifier estimates arrival-delay risk after departure and is evaluated on a later, unseen month.
- **Dashboard:** Streamlit presents flight punctuality, delays, cancellations, airport and airline performance, delay causes, historical delay-risk results, and sampled aircraft trajectories.

The two sources serve different purposes and are **not joined or matched to each other**.

## Architecture

```mermaid
flowchart LR
  A[BTS monthly files] --> B[Bronze archives]
  B --> C[PySpark validation and deduplication]
  C --> D[Silver Parquet]
  D --> ML[scikit-learn delay-risk model]
  ML --> M[Historical test metrics + examples]
  D --> E[PostgreSQL staging]
  E --> F[dbt models]
  F --> G[Analytics marts]
  H[Historical ADS-B sample] --> I[Replay events]
  I --> J[Kafka]
  J --> K[Spark Structured Streaming]
  K --> L[Silver Parquet + checkpoint]
  L --> E
  G --> N[Streamlit dashboard snapshot]
  M --> N
```

For transformation details, data contracts, model grains, and target-specific setup, see the [architecture notes](docs/architecture.md) and [data dictionary](docs/data_dictionary.md).

## Data included in the current snapshot

| Source | Snapshot coverage | Purpose |
| --- | --- | --- |
| BTS TranStats | May–July 2026; 1,851,282 scheduled flight records across 13 reporting airlines and 354 airports | Batch analysis of punctuality, delays, cancellations, diversions, routes, and reported delay causes |
| ADSB.aero | 40 flights sampled around JFK on 7 October 2026; 2,114 observations after validation and deduplication | Replayable historical trajectory sample for the streaming pipeline |

The repository includes an aggregated dashboard snapshot and a capped sample of held-out ML examples, not the full BTS flight-level dataset. ADS-B represents a bounded historical sample, not a live air-traffic feed.

## Run the dashboard demo

The public demo uses a bundled aggregate snapshot and **does not require database credentials or a running pipeline**.

```powershell
python -m pip install -r dashboard/requirements.txt
python -m streamlit run dashboard/app.py
```

Then open the local URL printed by Streamlit.

## Reproduce the ML evaluation

The **Delay risk** view estimates whether a flight will arrive at least 15 minutes late after its departure delay is known. The bundled results use May for training, June for probability calibration, and July as the untouched test month. They are a historical backtest, not a live or pre-departure forecast.

To train and export the model from BTS Silver data:

```powershell
python -m pip install -e ".[ml]"
make ml-train
```

The July holdout achieved 0.911 average precision and a 0.067 Brier score, compared with 0.283 test prevalence and a 0.208 constant-rate Brier baseline. The view also compares against a simple departure-delay rule. See the [ML study](docs/ml.md) for the target definition, features, validation policy, and limitations.

## Run the data platform locally

FlightPulse provides Docker Compose services for Kafka and PostgreSQL, a Python CLI, and a PowerShell runner designed for Windows. For full setup and pipeline commands, follow the [architecture notes](docs/architecture.md) and inspect the root `Makefile` / `flightpulse.ps1` scripts. The first Spark JDBC/Kafka runs may download connector JARs from Maven Central.

The optional Snowflake path requires a configured Snowflake account, role, warehouse, and credentials; it is not needed for the dashboard demo. See [Snowflake implementation notes](docs/snowflake.md).

## Data quality and engineering choices

- Preserve source archives and a SHA-256 manifest for BTS ingestion.
- Quarantine invalid critical BTS fields and invalid ADS-B coordinates rather than silently including them.
- Deduplicate flight legs using a composite identity; keep unreported delay measurements null rather than replacing them with zero.
- Use Spark checkpoints for replayable Kafka streaming and recovery.
- Validate BTS arrival-delay labels and compare ML scores with explicit, time-ordered baselines.
- Test Python processing and dbt models with pytest, seeded PostgreSQL fixtures, and GitHub Actions CI.

Metrics and their precise definitions are documented in [metrics](docs/metrics.md).

## Repository structure

```text
src/flightpulse/       BTS and ADS-B ingestion, Spark processing, Kafka streaming, ML training
dbt/models/            staging, facts, dimensions, and analytical marts
dashboard/             Streamlit application and bundled snapshot
scripts/               snapshot utilities, CI seeding, optional Snowflake loader
tests/                 deterministic Python tests and fixtures
docs/                  architecture, data dictionary, sources, metrics, and ML study
```

## Limitations

- The ADS-B pipeline processes a bounded historical sample through replay; it is not a live feed.
- BTS snapshot coverage ends in July 2026.
- The two data sources are kept separate and are not entity-matched.
- The dashboard uses bundled aggregates; it does not query the databases live.
- The delay-risk model uses observed departure delay, so it is not a pre-departure prediction; bundled BTS coverage ends in July 2026.
- Snowflake is an optional, implemented target that requires an account and proper privileges.
