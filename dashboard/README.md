# Interactive dashboard

The dashboard turns the FlightPulse analytics snapshot into a set of operational views. It combines BTS monthly flight-performance aggregates with a separate, bounded ADS-B trajectory sample. The displayed airport and airline labels use readable names; search also accepts airport and carrier codes.

## Views

| View | What it answers |
| --- | --- |
| **Overview** | How many flights were scheduled? What share arrived on time? How did average arrival delay, cancellations, and diversions change over the selected period? |
| **Airports** | How do arrival and departure performance compare by airport? Search by city or code and see every matching airport, not only the busiest ones. |
| **Airlines** | How do reporting carriers compare on punctuality, delay, cancellations, and diversions? Search by airline name or code. |
| **Delay causes** | Which reported BTS categories account for delay minutes, and how do they change over time? |
| **ADS-B** | Where did a selected aircraft observation track travel, and how did altitude and ground speed change over time? |

## Interpreting the metrics

- Arrival punctuality counts flights with an arrival delay below 15 minutes, after excluding cancelled and diverted flights and flights with an unknown arrival delay. Early arrivals count as on time.
- Cancellation and diversion rates use all scheduled flight records as their denominator.
- Negative delays represent early departures or arrivals. Missing delay and cause values remain unknown rather than being treated as zero.
- Delay cause categories are independently reported and are not expected to sum to total delay.
- ADS-B observations describe the selected historical sample and are not linked to BTS flight records.

## Snapshot contents

[`data/snapshot/`](data/snapshot/) contains daily airport and airline metrics, compact delay-cause summaries, route performance, ADS-B observation points, and display-name lookups. The BTS dashboard data is aggregated; individual BTS flight records and database credentials are not included. The snapshot covers BTS flights from May through July 2026 and an ADS-B sample around JFK from 7 October 2026.
