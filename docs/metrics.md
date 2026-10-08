# Metric definitions

## BTS flight measures

- **Scheduled flights:** count of BTS flight records, including canceled and diverted records.
- **On-time arrivals:** among flights that are not canceled or diverted and have a valid arrival-delay value, count delays below 15 minutes divided by eligible arrivals. A negative delay is early and on time.
- **Average arrival delay:** mean of the observed arrival-delay minutes for non-canceled, non-diverted flights. SQL aggregates ignore nulls.
- **Cancellation rate:** canceled records divided by all scheduled records in the selected group.
- **Diversion rate:** diverted records divided by all scheduled records in the selected group.
- **Departure airport performance:** `airport_daily_performance` rows with role `origin` use departure delays and departure punctuality.
- **Arrival airport performance:** rows with role `destination` use arrival delays and arrival punctuality, excluding canceled and diverted flights from the eligible denominator.
- **Delay causes:** carrier, weather, NAS, security, and late aircraft minutes are preserved independently. Missing causes remain null and the causes are not assumed to sum to total delay.

## ADS-B observations

Each row in `fact_adsb_observations` represents a single timestamped trajectory point. Longitude and latitude are WGS84 degrees; altitude is feet from the source path where present; speed and vertical rate retain the source units indicated by the API (`knots` and feet/minute). Observations without valid coordinates or timestamp are quarantined.

## Interpretation

These measures describe reported BTS operations and the bounded ADS-B sample. They do not imply that ADS-B flights have been matched to BTS records, and they do not predict future delay.
