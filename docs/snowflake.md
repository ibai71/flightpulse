# Snowflake target

FlightPulse includes an optional Snowflake warehouse path alongside the local PostgreSQL demo. It demonstrates warehouse setup, role-based access, staged Parquet ingestion with `PUT` and `COPY INTO`, load auditing, and dbt transformations in Snowflake. The shared dbt project keeps the business models and KPI definitions consistent across both targets.

## Data flow

1. Run the local pipelines to produce validated BTS and, optionally, ADS-B Silver Parquet files.
2. `scripts/load_snowflake.py` uploads those files to an internal stage, loads replacement landing tables, and records file and row counts in `LANDING.LOAD_AUDIT`.
3. dbt reads the landing tables through staging models and creates facts, dimensions, and performance marts in `FLIGHTPULSE.ANALYTICS`.

Raw BTS archives, local source responses, and credentials are not uploaded by this process. If there are no ADS-B Silver files, the existing Snowflake ADS-B landing snapshot is left unchanged.

## Account setup

The setup script is intended to run once in a Snowflake SQL worksheet using a role authorized to create the project resources (the script selects `ACCOUNTADMIN`). It creates the `FLIGHTPULSE_ROLE`, an X-Small warehouse with auto-suspend, the database and schemas, a Parquet file format and stage, landing tables, and a load audit table. It grants the project role the required schema privileges and transfers ownership of the landing objects.

Grant the project role to the Snowflake user separately, substituting the login name:

```sql
GRANT ROLE FLIGHTPULSE_ROLE TO USER <your_login>;
```

Configuration belongs in a private `.env` file based on `.env.example`. Use the account identifier shown in Snowflake, not the server URL. The password is prompted without echo and is not saved. The Snowflake optional dependencies are installed with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,snowflake]"
```

Run the loader and dbt target from the project environment after generating BTS Silver data:

```powershell
.\.venv\Scripts\python.exe scripts\load_snowflake.py
.\.venv\Scripts\python.exe -m flightpulse.cli dbt-snowflake-run
.\.venv\Scripts\python.exe -m flightpulse.cli dbt-snowflake-test
```

On Linux or WSL, the equivalent Make target is `make snowflake-pipeline` after installing the project and configuring the account. The role needs access to the warehouse, database, schemas, stage and file format, plus permission to create or replace landing and analytics objects.

## Current project status

The Snowflake setup SQL, Parquet loader, connector configuration, and dbt-snowflake target are included in the repository. Running them still depends on a valid Snowflake login and correctly granted role privileges. The cloud connection and load are not considered validated until the loader, dbt models, and dbt tests complete successfully in an accessible account.

The local PostgreSQL path and checked-in dashboard snapshot are independent of Snowflake. They remain the reproducible demo path when cloud access is unavailable or a trial account expires. Keep the warehouse suspended when it is not in use.
