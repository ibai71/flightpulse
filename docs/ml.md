# Machine-learning study

## Portfolio decision

The first model answers a time-bounded operational question: **once a flight has departed, what is the chance it will arrive at least 15 minutes late?** BTS provides both the observed departure delay and the official `ArrDel15` outcome for the same flight. This makes the prediction point explicit and supports a supervised, chronological evaluation with a passenger-friendly probability in the dashboard.

The bundled BTS sample contains 1,851,282 flight records from May through July 2026. After excluding cancellations, diversions, and rows without the required state or outcome, 1,811,579 flights are eligible. The on-time/late target is about 25% across the whole period and rises from 21.4% in May to 28.3% in July. This drift is why random train/test splits would give an overly optimistic and less realistic estimate.

| Candidate | Evidence in FlightPulse | Decision |
| --- | --- | --- |
| Arrival-delay risk classification at departure | 1.81M labeled flights; target is BTS `ArrDel15`; known departure delay is available as an input at the stated prediction point | **First model.** Outputs a probability for the official 15-minute definition and can be compared with a simple departure-delay rule. |
| Arrival-delay minutes regression at departure | Copying departure delay directly to arrival has July MAE 6.36 minutes, versus 23.49 minutes for always predicting zero | Keep as a strong benchmark and possible follow-up. A learned model must improve on this carry-forward rule to add value. |
| Airport-day anomaly detection | The snapshot has 62,875 airport/date/role rows across 354 airports and 92 days | Better-grounded anomaly use case than the ADS-B sample, but no labeled anomalies exist and each airport has only about three months of history. Defer until it can be validated against reviewed incidents or controlled spike-injection scenarios. |
| ADS-B trajectory anomaly detection | 2,114 observation points from 40 flights on one day, independent of BTS | Do not use as the first ML feature. The sample is too small to establish a reliable normal-operation baseline or validate anomaly alerts. |
| Aircraft-rotation delay propagation | Bronze BTS includes a tail number for 99.8% of rows (5,943 unique aircraft in this snapshot), but Silver does not retain it | Strong portfolio extension. It needs reliable flight sequencing across airport time zones and strict as-of feature construction to prevent future-leg leakage. |

This scope demonstrates more than model fitting: a defined prediction time, source-label quality, a simple operational baseline, temporal evaluation, probability calibration, artifact export, and a human-readable result. That emphasis follows practical ML guidance to start with measurable baselines and invest in pipeline tests and monitoring ([Google Rules of ML](https://developers.google.com/machine-learning/guides/rules-of-ml/), [ML Test Score](https://research.google/pubs/whats-your-ml-test-score-a-rubric-for-ml-production-systems/)). Research on short-term flight features also studies whether the preceding flight's delay improves predictions ([Schösser and Schönberger](https://hrcak.srce.hr/293664)).

## Target, inputs, and label quality

- **Target:** BTS `ArrDel15`, where 1 means arrival delay of at least 15 minutes. Cancelled and diverted flights are excluded.
- **Prediction point:** after departure, when `DepDelayMinutes` is observed. The dashboard must not describe this as a pre-departure forecast or live prediction.
- **Input features:** observed departure delay; airline; origin; destination; distance; day of week; and scheduled departure time represented cyclically.
- **Excluded from inputs:** arrival delay and `ArrDel15`, actual air time, reported delay causes, and ADS-B fields. These are unavailable or reveal the outcome at the chosen prediction point.
- **Source issue:** BTS stores `ArrDel15` as decimal text (`0.00` / `1.00`). Casting directly to an integer made the checked-in Silver label null. The BTS transform now parses through a numeric type and checks eligible-label completeness and agreement with the 15-minute threshold.
- **Legacy snapshot:** the checked-in Silver files predate that transform fix. For reproducibility, training allows a fallback only when all eligible `ArrDel15` labels are null; it derives the label from `ArrDelayMinutes >= 15` and records that source in the report. Partial missingness or disagreement is an error. Rebuilding BTS Silver restores the official parsed field.
- BTS `DepDelayMinutes` and `ArrDelayMinutes` are non-negative minute measures; early/on-time values are recorded as zero. The signed BTS fields `DepDelay` and `ArrDelay` are not currently curated.

## Training and evaluation

`make ml-train` fits a regularized logistic classifier using the earlier months, calibrates its probabilities with the immediately following month, and evaluates once on the latest month. With the current snapshot the split is May train, June calibration, July test. With a longer history, earlier months join training while the latest two months remain reserved for calibration and final testing.

The model uses one-hot encoded airline and airport categories plus numeric delay, distance, weekday, and cyclical-hour features. Unknown categories are tolerated. The calibrator is fitted on June only; July is not used to select features or tune the model.

Two baselines are reported:

1. A simple rule predicts a late arrival when departure delay is at least 15 minutes. On July, it reaches 89.9% accuracy, 81.1% precision, 83.7% recall, and 82.4% F1.
2. A constant probability equal to the training late-arrival rate is the probability baseline for Brier score. Its average precision equals the test prevalence (28.3%) for an uninformative ranking.

The model is marked **validated** only when July average precision exceeds the July late-arrival rate and its Brier score is lower than the training-rate baseline. Otherwise, the dashboard labels it **experimental**. A lower Brier score is better; no operational alert threshold is claimed.

The CLI writes:

- `dashboard/data/snapshot/delay_risk_metrics.json`: model identity, target and feature policy, label source, chronological split, baseline metrics, model metrics, and validation status.
- `dashboard/data/snapshot/delay_risk_holdout.csv`: up to 500 deterministic July examples with flight date, route, airline, scheduled time, observed departure delay, estimated probability, and actual outcome.
- `data/models/delay_risk.joblib`: local model and calibrator artifact; this is ignored by Git and is not needed to view the dashboard.

The dashboard uses the metrics and capped examples, not a serving endpoint. Its example selector shows an out-of-time estimate beside the actual result. The user-facing wording is historical and explicitly says the model already knows the departure delay.

## Limits and next experiments

The snapshot covers only May–July 2026. It cannot establish performance across seasons, future months, new airline schedules, or severe weather events. There is no live feed for serving updated scores. Cancelled and diverted flights are outside the target. A historical backtest does not establish operational impact.

The next high-value experiment is aircraft-rotation propagation: retain the BTS tail number and actual timestamps, add a versioned airport timezone mapping, construct only the preceding leg information available by the current flight's departure, and compare against the current model on a later-month holdout. Airport-day anomaly detection is another candidate once a review process can validate flagged disruptions. Neither should be combined with the first model until its feature timing and evaluation are reliable.
