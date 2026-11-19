"""Train and export an at-departure arrival-delay risk model."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from flightpulse.config import PROJECT_ROOT, data_dir


MODEL_FEATURES = [
    "airline_code",
    "origin_code",
    "destination_code",
    "flight_day_of_week",
    "departure_delay_minutes",
    "distance_miles",
    "scheduled_hour_sin",
    "scheduled_hour_cos",
]
CATEGORICAL_FEATURES = [
    "airline_code",
    "origin_code",
    "destination_code",
    "flight_day_of_week",
]
NUMERIC_FEATURES = [
    "departure_delay_minutes",
    "distance_miles",
    "scheduled_hour_sin",
    "scheduled_hour_cos",
]
SOURCE_COLUMNS = [
    "flight_id",
    "flight_date",
    "airline_code",
    "origin_code",
    "destination_code",
    "scheduled_departure_hhmm",
    "departure_delay_minutes",
    "arrival_delay_minutes",
    "arrival_delayed_15",
    "cancelled",
    "diverted",
    "distance_miles",
]


def _bool_series(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False)
    return values.astype("string").str.lower().isin(["true", "1", "1.0", "yes"])


def _scheduled_hour_features(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    hhmm = pd.to_numeric(values, errors="coerce")
    hours = np.floor(hhmm / 100)
    minutes = hhmm % 100
    valid = ((hours.between(0, 23) & minutes.between(0, 59)) | hhmm.eq(2400))
    decimal_hour = (hours + minutes / 60).where(valid)
    decimal_hour = decimal_hour.mask(hhmm.eq(2400), 0.0)
    radians = decimal_hour * (2 * np.pi / 24)
    return np.sin(radians), np.cos(radians)


def prepare_model_frame(source: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Validate the outcome and construct features available at departure time."""
    missing = sorted(set(SOURCE_COLUMNS) - set(source.columns))
    if missing:
        raise ValueError(f"BTS Silver is missing required ML columns: {', '.join(missing)}")

    frame = source.copy()
    frame["flight_date"] = pd.to_datetime(frame["flight_date"], errors="coerce")
    operational_flags_known = frame["cancelled"].notna() & frame["diverted"].notna()
    frame["cancelled"] = _bool_series(frame["cancelled"])
    frame["diverted"] = _bool_series(frame["diverted"])
    frame["arrival_delay_minutes"] = pd.to_numeric(frame["arrival_delay_minutes"], errors="coerce")
    frame["departure_delay_minutes"] = pd.to_numeric(frame["departure_delay_minutes"], errors="coerce")
    frame["arrival_delayed_15"] = pd.to_numeric(frame["arrival_delayed_15"], errors="coerce")

    eligible = (
        operational_flags_known
        & ~frame["cancelled"]
        & ~frame["diverted"]
        & frame["arrival_delay_minutes"].notna()
    )
    threshold_label = frame["arrival_delay_minutes"].ge(15).astype("int8")
    known_labels = frame.loc[eligible, "arrival_delayed_15"].dropna()
    invalid_labels = ~known_labels.isin([0, 1])
    if invalid_labels.any():
        raise ValueError("BTS ArrDel15 must contain only 0 or 1 for completed flights")
    if not known_labels.empty:
        known = frame["arrival_delayed_15"].notna() & eligible
        mismatches = known_labels.astype("int8").ne(threshold_label.loc[known])
        if mismatches.any():
            raise ValueError("BTS ArrDel15 does not match the 15-minute arrival-delay threshold")

    label_source = "BTS ArrDel15"
    missing_eligible_labels = eligible & frame["arrival_delayed_15"].isna()
    if missing_eligible_labels.any():
        if not known_labels.empty:
            raise ValueError(
                "ArrDel15 is partially missing on completed flights; rebuild BTS Silver before training"
            )
        # Compatibility with the checked-in legacy Silver snapshot: its integer cast
        # turned BTS decimal strings (0.00/1.00) into null. BTS defines ArrDel15 as
        # ArrDelayMinutes >= 15; the raw snapshot was checked against that rule.
        frame.loc[eligible, "arrival_delayed_15"] = threshold_label.loc[eligible]
        label_source = "ArrDelayMinutes threshold (legacy Silver compatibility)"

    frame["flight_day_of_week"] = frame["flight_date"].dt.dayofweek.astype("Int64").astype("string")
    frame["scheduled_hour_sin"], frame["scheduled_hour_cos"] = _scheduled_hour_features(
        frame["scheduled_departure_hhmm"]
    )
    frame["distance_miles"] = pd.to_numeric(frame["distance_miles"], errors="coerce")

    # An at-departure score needs the observed departure delay. Missing outcomes,
    # departure states, or dates are not imputed into fabricated flight events.
    usable = (
        eligible
        & frame["arrival_delayed_15"].notna()
        & frame["departure_delay_minutes"].notna()
        & frame["flight_date"].notna()
    )
    model_frame = frame.loc[usable, SOURCE_COLUMNS + [
        "flight_day_of_week", "scheduled_hour_sin", "scheduled_hour_cos",
    ]].copy()
    model_frame["arrival_delayed_15"] = model_frame["arrival_delayed_15"].astype("int8")
    for name in CATEGORICAL_FEATURES:
        model_frame[name] = model_frame[name].fillna("UNKNOWN").astype(str)
    model_frame["target"] = model_frame["arrival_delayed_15"].astype("int8")
    model_frame = model_frame.sort_values(["flight_date", "flight_id"], kind="stable").reset_index(drop=True)
    return model_frame, label_source


def chronological_months(frame: pd.DataFrame) -> tuple[list[pd.Period], pd.Period, pd.Period]:
    months = sorted(frame["flight_date"].dt.to_period("M").dropna().unique())
    if len(months) < 3:
        raise ValueError("At least three distinct BTS months are required for train/calibration/test")
    return months[:-2], months[-2], months[-1]


def _classification_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    predictions = probabilities >= 0.5
    return {
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "precision_at_50_percent": float(precision_score(y_true, predictions, zero_division=0)),
        "recall_at_50_percent": float(recall_score(y_true, predictions, zero_division=0)),
        "f1_at_50_percent": float(f1_score(y_true, predictions, zero_division=0)),
    }


def _heuristic_metrics(y_true: np.ndarray, departure_delays: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    predictions = departure_delays >= 15
    return {
        "rule": "departure_delay_minutes >= 15",
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
    }


def train_delay_risk(
    *,
    silver_path: Path | None = None,
    output_dir: Path | None = None,
    model_dir: Path | None = None,
) -> dict[str, Any]:
    """Train a calibrated classifier and export holdout metrics and examples."""
    try:
        from joblib import dump
        from sklearn.compose import ColumnTransformer
        from sklearn.impute import SimpleImputer
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import SGDClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
    except ImportError as error:
        raise RuntimeError(
            "Delay-risk training needs the optional ML dependencies. Install with `python -m pip install -e '.[ml]'`."
        ) from error

    silver_path = silver_path or data_dir() / "silver" / "bts"
    output_dir = output_dir or PROJECT_ROOT / "dashboard" / "data" / "snapshot"
    model_dir = model_dir or data_dir() / "models"
    if not silver_path.exists():
        raise FileNotFoundError(f"BTS Silver data not found at {silver_path}; run `make bts-pipeline` first.")

    source = pd.read_parquet(silver_path, columns=SOURCE_COLUMNS)
    frame, label_source = prepare_model_frame(source)
    train_months, calibration_month, test_month = chronological_months(frame)
    month = frame["flight_date"].dt.to_period("M")
    train_mask = month.isin(train_months)
    calibration_mask = month.eq(calibration_month)
    test_mask = month.eq(test_month)
    train = frame.loc[train_mask]
    calibration = frame.loc[calibration_mask]
    test = frame.loc[test_mask]
    if min(len(train), len(calibration), len(test)) == 0:
        raise ValueError("The chronological BTS split produced an empty train, calibration, or test period")
    y_train = train["target"].to_numpy(dtype=np.int8)
    y_calibration = calibration["target"].to_numpy(dtype=np.int8)
    y_test = test["target"].to_numpy(dtype=np.int8)
    if len(np.unique(y_train)) != 2 or len(np.unique(y_calibration)) != 2 or len(np.unique(y_test)) != 2:
        raise ValueError("Each chronological period must contain both on-time and delayed arrivals")

    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler(with_mean=False)),
    ])
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("one_hot", OneHotEncoder(handle_unknown="ignore", min_frequency=50, dtype=np.float32)),
    ])
    preprocessing = ColumnTransformer([
        ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ("numeric", numeric_pipeline, NUMERIC_FEATURES),
    ], sparse_threshold=1.0)
    classifier = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=0.0001,
        max_iter=30,
        tol=0.001,
        random_state=42,
        average=True,
    )
    model = Pipeline([("features", preprocessing), ("classifier", classifier)])
    model.fit(train[MODEL_FEATURES], y_train)

    calibration_raw = model.predict_proba(calibration[MODEL_FEATURES])[:, 1]
    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    calibrator.fit(calibration_raw, y_calibration)
    test_raw = model.predict_proba(test[MODEL_FEATURES])[:, 1]
    test_probabilities = np.clip(calibrator.predict(test_raw), 0.0, 1.0)

    model_metrics = _classification_metrics(y_test, test_probabilities)
    train_prevalence = float(y_train.mean())
    test_prevalence = float(y_test.mean())
    prevalence_brier = float(np.mean((train_prevalence - y_test) ** 2))
    calibration_edges = [-0.000001, 0.2, 0.4, 0.6, 0.8, 1.000001]
    calibration_labels = ["0–19%", "20–39%", "40–59%", "60–79%", "80–100%"]
    calibration_frame = pd.DataFrame({
        "probability": test_probabilities,
        "target": y_test,
    })
    calibration_frame["risk_band"] = pd.cut(
        calibration_frame["probability"],
        bins=calibration_edges,
        labels=calibration_labels,
        right=False,
        include_lowest=True,
    )
    calibration_bands = [
        {
            "risk_band": str(risk_band),
            "flights": int(group["target"].count()),
            "estimated_probability": float(group["probability"].mean()),
            "observed_late_rate": float(group["target"].mean()),
        }
        for risk_band, group in calibration_frame.groupby("risk_band", observed=False)
        if len(group)
    ]
    baseline_heuristic = _heuristic_metrics(
        y_test,
        test["departure_delay_minutes"].to_numpy(dtype=float),
    )
    validated = (
        model_metrics["average_precision"] > test_prevalence
        and model_metrics["brier_score"] < prevalence_brier
    )
    report: dict[str, Any] = {
        "model": "regularized_logistic_regression_sgd",
        "prediction_point": "after departure, when departure delay is observed",
        "target": "BTS ArrDel15: arrival delay of at least 15 minutes",
        "label_source": label_source,
        "features": MODEL_FEATURES,
        "excluded_features": [
            "arrival_delay_minutes", "arrival_delayed_15", "air_time_minutes",
            "delay_cause_minutes", "ADS-B observations",
        ],
        "split": {
            "train_months": [str(value) for value in train_months],
            "calibration_month": str(calibration_month),
            "test_month": str(test_month),
            "train_rows": int(len(train)),
            "calibration_rows": int(len(calibration)),
            "test_rows": int(len(test)),
        },
        "test_positive_rate": test_prevalence,
        "calibration_bands": calibration_bands,
        "training_prevalence_baseline": {
            "probability": train_prevalence,
            "average_precision": test_prevalence,
            "brier_score": prevalence_brier,
        },
        "departure_delay_rule_baseline": baseline_heuristic,
        "model_metrics": model_metrics,
        "validation": {
            "status": "validated" if validated else "experimental",
            "criteria": {
                "average_precision_above_test_prevalence": model_metrics["average_precision"] > test_prevalence,
                "brier_below_training_prevalence_baseline": model_metrics["brier_score"] < prevalence_brier,
            },
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "delay_risk_metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    sample_count = min(500, len(test))
    sample_indices = test.sample(n=sample_count, random_state=42).index
    sample = test.loc[sample_indices, [
        "flight_id", "flight_date", "airline_code", "origin_code", "destination_code",
        "scheduled_departure_hhmm", "departure_delay_minutes", "arrival_delayed_15",
        "arrival_delay_minutes",
    ]].copy()
    sample["predicted_probability"] = test_probabilities[test.index.get_indexer(sample_indices)]
    sample = sample.sort_values(["flight_date", "flight_id"], kind="stable")
    sample["flight_date"] = sample["flight_date"].dt.strftime("%Y-%m-%d")
    sample.to_csv(output_dir / "delay_risk_holdout.csv", index=False)
    dump({"model": model, "calibrator": calibrator, "metadata": report}, model_dir / "delay_risk.joblib")

    print(
        "Delay-risk model: "
        f"{report['validation']['status']} | test={len(test):,} | "
        f"AP={model_metrics['average_precision']:.3f} | "
        f"Brier={model_metrics['brier_score']:.4f} (baseline {prevalence_brier:.4f})"
    )
    print(f"Metrics and examples: {output_dir}")
    return report
