# Power BI dashboard build guide

The Power BI file is created and saved locally in Power BI Desktop; `.pbix` files are ignored by Git. Start Compose, run both pipelines, then connect through **Get data → PostgreSQL database**:

- Server: `localhost:5432`
- Database: value of `POSTGRES_DB` in `.env` (default `flightpulse`)
- Schema: `analytics`
- Authentication: PostgreSQL credentials from `.env`

Load `fact_flights`, the dimensions, the daily aggregates, and `fact_adsb_observations`. Use the following report pages and measures.

Create one-to-many, single-direction relationships from `dim_date[date_key]` to the date field on `fact_flights`, `airport_daily_performance`, `airline_daily_performance`, and `delay_causes`; from `dim_airline[airline_id]` to the airline ID on the flight fact and airline/delay aggregates; and from `dim_airport[airport_id]` to `airport_daily_performance[airport_id]`. If you need separate origin and destination slicers on `fact_flights`, duplicate `dim_airport` in Power Query and use one copy for each airport role.

## Overview

Cards: scheduled flights, arrival on-time percentage, average arrival delay, cancellation rate, and diversion rate. Use `airline_daily_performance` or `fact_flights` for date/airline slicers. Keep cancellations and diversions in the denominator for their corresponding rates; exclude them and records with unknown arrival delay from the on-time denominator.

Suggested DAX measures:

```DAX
Scheduled Flights = COUNTROWS(fact_flights)

Eligible Arrivals =
CALCULATE(
    COUNTROWS(fact_flights),
    fact_flights[cancelled] = FALSE(),
    fact_flights[diverted] = FALSE(),
    NOT ISBLANK(fact_flights[arrival_delay_minutes])
)

On-Time Arrival % =
DIVIDE(
    CALCULATE(
        COUNTROWS(fact_flights),
        fact_flights[cancelled] = FALSE(),
        fact_flights[diverted] = FALSE(),
        NOT ISBLANK(fact_flights[arrival_delay_minutes]),
        fact_flights[arrival_delay_minutes] < 15
    ),
    [Eligible Arrivals]
)

Average Arrival Delay =
CALCULATE(
    AVERAGE(fact_flights[arrival_delay_minutes]),
    fact_flights[cancelled] = FALSE(),
    fact_flights[diverted] = FALSE()
)

Cancellation % =
DIVIDE(CALCULATE(COUNTROWS(fact_flights), fact_flights[cancelled] = TRUE()), [Scheduled Flights])

Diversion % =
DIVIDE(CALCULATE(COUNTROWS(fact_flights), fact_flights[diverted] = TRUE()), [Scheduled Flights])
```

## Airport Performance

Use `airport_daily_performance` as a matrix with airport code, `airport_role`, scheduled flights, average delay, on-time rate, cancellation rate, and diversion rate. Add date and role slicers. There are no airport coordinates in the selected source columns, so use a ranked table rather than a map.

## Airline Performance

Use `airline_daily_performance` for airline ranking by flights, average arrival delay, on-time rate, cancellation rate, and diversion rate. Add a date trend and a table of carriers with the lowest on-time percentage.

## Delay Analysis

Use `delay_causes` for stacked bars by cause and airline, a date trend of total delay minutes, and a route detail table. Null cause values are not converted to zero; these records are excluded from cause totals.

## ADS-B Trajectories

Use `fact_adsb_observations` with flight ID and event timestamp as filters. Plot longitude/latitude on a map, altitude and ground speed over event time, and provide callsign, aircraft type, and endpoint fields as slicers. This page describes the bounded ADS-B sample and has no BTS flight matching.
