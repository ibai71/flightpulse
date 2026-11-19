# Interactive dashboard

The dashboard turns the FlightPulse analytics snapshot into a set of operational views. It combines BTS monthly flight-performance aggregates with a separate, bounded ADS-B trajectory sample. The displayed airport and airline labels use readable names; search also accepts airport and carrier codes.

## Views

| View | What it answers |
| --- | --- |
| **Overview** | How many flights were scheduled? What share arrived on time? How did average arrival delay, cancellations, and diversions change over the selected period? |
| **Airports** | How do arrival and departure performance compare by airport? Search by city or code and see every matching airport, not only the busiest ones. |
| **Airlines** | How do reporting carriers compare on punctuality, delay, cancellations, and diversions? Search by airline name or code. |
| **Delay causes** | Which reported BTS categories account for delay minutes, and how do they change over time? |
| **Delay risk** | For a flight that has departed, how likely is it to arrive at least 15 minutes late? How did the model perform on a later, unseen month? |
| **ADS-B** | Where did a selected aircraft observation track travel, and how did altitude and ground speed change over time? |

## Interpreting the metrics

- Arrival punctuality counts flights with an arrival delay below 15 minutes, after excluding cancelled and diverted flights and flights with an unknown arrival delay. Early arrivals count as on time.
- Cancellation and diversion rates use all scheduled flight records as their denominator.
- BTS `DepDelayMinutes` and `ArrDelayMinutes` are non-negative minute fields; early/on-time flights are represented as zero. Missing delay and cause values remain unknown rather than being treated as zero.
- Delay cause categories are independently reported and are not expected to sum to total delay.
- ADS-B observations describe the selected historical sample and are not linked to BTS flight records.

## Delay risk model

The **Delay risk** view shows an at-departure estimate: it uses the observed departure delay to estimate whether a completed flight will arrive at least 15 minutes late. It is a historical backtest, not a live service or a prediction made before departure. The view reports a chronological holdout evaluation, compares the model with simple baselines, and lets readers inspect a small sample of test flights and their actual outcomes. Cancelled and diverted flights are excluded.

The training command reads BTS Silver Parquet, trains on earlier months, calibrates on the preceding month, and reserves the latest month for testing:

```powershell
python -m pip install -e ".[ml]"
make ml-train
```

The exported `delay_risk_metrics.json` and `delay_risk_holdout.csv` files are bundled with the dashboard snapshot, so the view does not require a database or model-serving process. For the modeling decision, baselines, feature policy, and limitations, see [`../docs/ml.md`](../docs/ml.md).

## Snapshot contents

[`data/snapshot/`](data/snapshot/) contains daily airport and airline metrics, compact delay-cause summaries, route performance, ADS-B observation points, display-name lookups, and the ML evaluation with a capped set of held-out examples. It does not include the full BTS flight-level dataset or database credentials. The snapshot covers BTS flights from May through July 2026 and an ADS-B sample around JFK from 7 October 2026.
