from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
from flightpulse.ml.delay_risk import MODEL_FEATURES, chronological_months, prepare_model_frame, train_delay_risk


def sample_rows(*, null_labels: bool = False) -> pd.DataFrame:
    rows = []
    for month in (5, 6, 7):
        for index in range(60):
            departure_delay = 25.0 if index % 2 else 0.0
            late = int(index % 2 == 1)
            rows.append({
                "flight_id": f"2026-{month:02d}-{index:04d}",
                "flight_date": f"2026-{month:02d}-{1 + index % 20:02d}",
                "airline_code": "AA" if index % 3 else "DL",
                "origin_code": "JFK" if index % 2 else "LAX",
                "destination_code": "LAX" if index % 2 else "JFK",
                "scheduled_departure_hhmm": 800 if index % 2 else 1600,
                "departure_delay_minutes": departure_delay,
                "arrival_delay_minutes": 20.0 if late else 0.0,
                "arrival_delayed_15": None if null_labels else late,
                "cancelled": False,
                "diverted": False,
                "distance_miles": 2475.0,
            })
    rows.append({
        "flight_id": "cancelled",
        "flight_date": "2026-07-25",
        "airline_code": "AA",
        "origin_code": "JFK",
        "destination_code": "LAX",
        "scheduled_departure_hhmm": 800,
        "departure_delay_minutes": None,
        "arrival_delay_minutes": None,
        "arrival_delayed_15": None,
        "cancelled": True,
        "diverted": False,
        "distance_miles": 2475.0,
    })
    return pd.DataFrame(rows)


def test_prepare_model_frame_uses_only_departure_available_features():
    prepared, label_source = prepare_model_frame(sample_rows())

    assert label_source == "BTS ArrDel15"
    assert len(prepared) == 180
    assert set(prepared.target.unique()) == {0, 1}
    assert set(MODEL_FEATURES).isdisjoint({"arrival_delay_minutes", "arrival_delayed_15"})
    assert prepared.loc[prepared.scheduled_departure_hhmm == 800, "scheduled_hour_sin"].nunique() == 1


def test_prepare_model_frame_recovers_the_legacy_all_null_label_snapshot():
    prepared, label_source = prepare_model_frame(sample_rows(null_labels=True))

    assert "legacy Silver compatibility" in label_source
    assert prepared.target.sum() == 90


def test_prepare_model_frame_rejects_inconsistent_bts_labels():
    source = sample_rows()
    source.loc[0, "arrival_delayed_15"] = 1

    with pytest.raises(ValueError, match="does not match"):
        prepare_model_frame(source)


def test_chronological_month_split_reserves_latest_two_months():
    frame, _ = prepare_model_frame(sample_rows())

    train_months, calibration_month, test_month = chronological_months(frame)

    assert [str(month) for month in train_months] == ["2026-05"]
    assert str(calibration_month) == "2026-06"
    assert str(test_month) == "2026-07"


def test_train_exports_metrics_holdout_sample_and_model(tmp_path):
    pytest.importorskip("sklearn")
    pytest.importorskip("pyarrow")
    source_path = tmp_path / "silver"
    output_path = tmp_path / "dashboard"
    model_path = tmp_path / "models"
    sample_rows().to_parquet(source_path, index=False)

    report = train_delay_risk(silver_path=source_path, output_dir=output_path, model_dir=model_path)

    assert report["split"]["test_rows"] == 60
    assert sum(band["flights"] for band in report["calibration_bands"]) == 60
    assert (output_path / "delay_risk_metrics.json").exists()
    assert len(pd.read_csv(output_path / "delay_risk_holdout.csv")) == 60
    assert (model_path / "delay_risk.joblib").exists()
