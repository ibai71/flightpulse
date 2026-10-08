# Data sources

## BTS Reporting Carrier On-Time Performance

- Official table: https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ
- Monthly ZIP pattern used by the ingestion code: `On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip` in TranStats' `PREZIP` directory.
- Default run: May–July 2026; explicitly pass `START_MONTH` / `END_MONTH` to select another period.
- The original ZIP and its manifest remain in `data/bronze/bts/archive`; the minimally parsed Bronze Parquet remains in `data/bronze/bts/parquet`.
- Fields retained for the model are declared in `src/flightpulse/processing/bts.py`. DOT carrier and airport IDs are used alongside display codes because codes can change or be reused.
- TranStats publishes data monthly. A download may fail if a month is not available or the public site's URL behavior changes; rerun for a published month after checking the official page.

## ADSB.aero

- API docs: https://adsb.aero/api/docs
- Airport lookup: `GET /api/v1/airports/{code}`; flight search: `POST /api/v1/query`; flight detail includes the per-flight trajectory.
- The job requests one UTC day, uses airport geometry, limits to 40 flights by default, and stores the raw response plus a flattened event file locally.
- Check `GET /api/v1/data-range` before selecting a date. The archive range can change. The pipeline does not assume API data is available on any fixed date.
- `include_path` data is needed for the ADS-B demo and therefore increases response size. The flight cap keeps the request bounded.

## Local data handling

No downloaded datasets or secrets are committed. API responses are retained only under ignored `data/` paths. Fixtures in the repository are small hand-authored examples used for tests.
