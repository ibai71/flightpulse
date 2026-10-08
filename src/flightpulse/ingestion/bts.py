from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flightpulse.config import data_dir, spark_session


BTS_URL = "https://www.transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"


def month_sequence(start_month: str, end_month: str) -> list[tuple[int, int]]:
    pattern = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
    if not pattern.fullmatch(start_month) or not pattern.fullmatch(end_month):
        raise ValueError("Months must use YYYY-MM format")
    start_year, start_num = (int(part) for part in start_month.split("-"))
    end_year, end_num = (int(part) for part in end_month.split("-"))
    if start_year < 1987:
        raise ValueError("The BTS Reporting Carrier On-Time Performance table starts in 1987")
    if (start_year, start_num) > (end_year, end_num):
        raise ValueError("start_month must not be after end_month")
    months: list[tuple[int, int]] = []
    year, month = start_year, start_num
    while (year, month) <= (end_year, end_num):
        months.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def _session() -> requests.Session:
    retry = Retry(total=4, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "FlightPulse data engineering portfolio/0.1"})
    return session


def ingest_month(year: int, month: int, root: Path | None = None) -> dict[str, object]:
    root = root or data_dir()
    key = f"year={year}/month={month:02d}"
    archive_dir = root / "bronze" / "bts" / "archive" / key
    parquet_dir = root / "bronze" / "bts" / "parquet" / key
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / "source.zip"
    partial_path = archive_dir / "source.zip.part"
    manifest_path = archive_dir / "manifest.json"
    url = BTS_URL.format(year=year, month=month)
    with _session().get(url, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        digest = hashlib.sha256()
        partial_path.unlink(missing_ok=True)
        with partial_path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    digest.update(chunk)
                    output.write(chunk)
    checksum = digest.hexdigest()
    if not zipfile.is_zipfile(partial_path):
        partial_path.unlink(missing_ok=True)
        raise ValueError(f"BTS download is not a ZIP archive: {urlparse(url).path}")
    os.replace(partial_path, zip_path)

    with tempfile.TemporaryDirectory(prefix="flightpulse-bts-") as temp_dir:
        with zipfile.ZipFile(zip_path) as archive:
            candidates = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not candidates:
                raise ValueError(f"No CSV file found in BTS archive for {year}-{month:02d}")
            member = candidates[0]
            extracted = Path(temp_dir) / Path(member).name
            with archive.open(member) as source, extracted.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)

        spark = spark_session("FlightPulse-BTS-Bronze")
        try:
            rows = (
                spark.read.option("header", True)
                .option("multiLine", False)
                .option("encoding", "UTF-8")
                .option("mode", "PERMISSIVE")
                .csv(str(extracted))
            )
            row_count = rows.count()
            rows.write.mode("overwrite").parquet(str(parquet_dir))
        finally:
            spark.stop()

    manifest = {
        "source": "BTS Reporting Carrier On-Time Performance",
        "source_url": url,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "month": month,
        "archive_member": member,
        "sha256": checksum,
        "source_rows": row_count,
        "bronze_parquet": str(parquet_dir.relative_to(root)),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"BTS {year}-{month:02d}: wrote {row_count:,} rows to {parquet_dir}")
    return manifest


def ingest_range(start_month: str, end_month: str, root: Path | None = None) -> list[dict[str, object]]:
    months = month_sequence(start_month, end_month)
    return [ingest_month(year, month, root=root) for year, month in months]
