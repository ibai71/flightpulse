# Data dictionary

## PostgreSQL `analytics`

| Relation | Grain | Main fields |
| --- | --- | --- |
| `fact_flights` | One BTS-reported flight leg | `flight_id`, `flight_date`, airline and airport IDs/codes, scheduled departure, delay minutes, canceled/diverted flags, distance, air time, delay causes |
| `dim_date` | One observed flight date | Date key, year, quarter, month, day of week |
| `dim_airline` | One DOT reporting-carrier ID | Airline ID and representative reporting code |
| `dim_airport` | One DOT airport ID | Airport ID and representative airport code |
| `airport_daily_performance` | Airport/date/role | Flight counts, average delay, punctuality, cancellation and diversion rates; role is `origin` or `destination` |
| `airline_daily_performance` | Airline/date | Flight counts, average arrival delay, punctuality and disruption rates |
| `route_performance` | Origin/destination pair | Flight counts, arrival delay, punctuality and disruption rates |
| `delay_causes` | Date/airline/route/cause | Count with cause reported and total/average cause minutes |
| `fact_adsb_observations` | One flight and UTC timestamp | Flight metadata (`operator_name`), airport endpoints, coordinates, altitude, track, speed, vertical rate |

## BTS source-to-Silver mapping

| BTS source field | Silver field | Meaning |
| --- | --- | --- |
| `FlightDate` | `flight_date` | Operating date; retained as date without timezone conversion |
| `DOT_ID_Reporting_Airline` | `airline_id` | Stable DOT reporting carrier ID |
| `Reporting_Airline` | `airline_code` | Reporting carrier display code |
| `Flight_Number_Reporting_Airline` | `flight_number` | Reported flight number, retained as text |
| `OriginAirportID`, `Origin` | `origin_airport_id`, `origin_code` | Origin identifier and code |
| `DestAirportID`, `Dest` | `destination_airport_id`, `destination_code` | Destination identifier and code |
| `CRSDepTime` | `scheduled_departure_hhmm` | Scheduled local HHMM value; not converted to a timezone-aware timestamp |
| `DepDelayMinutes`, `ArrDelayMinutes` | `departure_delay_minutes`, `arrival_delay_minutes` | Reported minutes; negative values are retained |
| `ArrDel15` | `arrival_delayed_15` | BTS 15-minute arrival-delay indicator |
| `Cancelled`, `Diverted` | `cancelled`, `diverted` | Boolean operational flags |
| `Distance`, `AirTime` | `distance_miles`, `air_time_minutes` | Reported distance and air time |
| `CarrierDelay`, `WeatherDelay`, `NASDelay`, `SecurityDelay`, `LateAircraftDelay` | Corresponding `*_delay_minutes` fields | Cause-specific delay minutes; null means unreported/not applicable |

The `staging` schema contains the latest loaded BTS rows and ADS-B observations. The `bronze`, `silver`, quarantine, quality reports, and checkpoints are local files under the ignored `data/` directory.
