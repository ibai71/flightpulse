from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def data_dir() -> Path:
    value = os.getenv("FLIGHTPULSE_DATA_DIR", "data")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def postgres_connection() -> dict[str, str]:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "flightpulse")
    return {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": os.getenv("POSTGRES_USER", "flightpulse"),
        "password": os.getenv("POSTGRES_PASSWORD", "flightpulse_local"),
        "jdbc_url": os.getenv("POSTGRES_JDBC_URL", f"jdbc:postgresql://{host}:{port}/{dbname}"),
    }


def spark_session(app_name: str, *, kafka: bool = False, jdbc: bool = False):
    from pyspark.sql import SparkSession

    packages = []
    if jdbc:
        packages.append(os.getenv("POSTGRES_JDBC_PACKAGE", "org.postgresql:postgresql:42.7.8"))
    if kafka:
        packages.append("org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.0")
    builder = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
    )
    if packages:
        builder = builder.config("spark.jars.packages", ",".join(packages))
    return builder.getOrCreate()
