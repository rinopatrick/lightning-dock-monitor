from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .profile import DATE_COLUMN, MAX_REPORT_GAP_DAYS, OUTPUT_COLUMN, flag_extreme_output


def build_warning_frame(daily: pd.DataFrame, threshold_pct: float = 10.0) -> tuple[pd.DataFrame, list[str]]:
    """Create next-report targets and features observable at prediction time."""
    frame = daily.copy().sort_values(DATE_COLUMN).reset_index(drop=True)
    frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN], errors="coerce")
    output = pd.to_numeric(frame[OUTPUT_COLUMN], errors="coerce")
    extreme, _ = flag_extreme_output(frame)
    frame[OUTPUT_COLUMN] = output.where(~extreme & output.gt(0))
    valid = frame.loc[frame[OUTPUT_COLUMN].notna()].copy().reset_index(drop=True)
    dates = valid[DATE_COLUMN]
    current = valid[OUTPUT_COLUMN]
    next_output = current.shift(-1)
    gap = (dates.shift(-1) - dates).dt.days
    target_drop = (next_output / current - 1.0) * 100.0
    frame_out = pd.DataFrame({
        "date": dates,
        "target_drop_pct": target_drop,
        "target": target_drop.le(-threshold_pct).astype("Int64"),
        "report_gap_to_target_days": gap,
    })
    frame_out.loc[gap.gt(MAX_REPORT_GAP_DAYS) | next_output.isna(), "target"] = pd.NA

    features: dict[str, pd.Series] = {
        "output_kw": current,
        "output_change_pct_1_report": (current / current.shift(1) - 1.0) * 100.0,
        "output_change_pct_2_reports": (current / current.shift(2) - 1.0) * 100.0,
        "days_since_previous_output": (dates - dates.shift(1)).dt.days,
        "source_report_count": pd.to_numeric(valid.get("source_report_count", 1), errors="coerce"),
        "duplicate_conflict_columns": pd.to_numeric(valid.get("duplicate_conflict_columns", 0), errors="coerce"),
    }
    for column in [c for c in valid.columns if c.startswith("well::")]:
        signal = pd.to_numeric(valid[column], errors="coerce")
        features[column] = signal
        features[column + "::change_1"] = signal.diff()

    feature_frame = pd.DataFrame(features).reset_index(drop=True)
    frame_out = pd.concat([frame_out, feature_frame], axis=1)
    frame_out = frame_out.loc[frame_out["target"].notna()].reset_index(drop=True)
    feature_names = list(feature_frame.columns)
    return frame_out, feature_names


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, probabilities: np.ndarray | None = None) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

    positives = int(np.sum(y_true == 1))
    negatives = int(np.sum(y_true == 0))
    false_alarms = int(np.sum((y_true == 0) & (y_pred == 1)))
    result: dict[str, Any] = {
        "n": int(len(y_true)),
        "positive_count": positives,
        "negative_count": negatives,
        "prevalence_pct": float(positives / len(y_true) * 100) if len(y_true) else None,
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "false_alarms_per_100": float(false_alarms / max(negatives, 1) * 100),
    }
    if probabilities is not None and len(np.unique(y_true)) == 2:
        result["average_precision"] = float(average_precision_score(y_true, probabilities))
    else:
        result["average_precision"] = None
    return result


def evaluate_threshold(daily: pd.DataFrame, threshold_pct: float = 10.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Chronological holdout, with a momentum heuristic and logistic regression."""
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt to run the warning model.") from exc

    data, feature_names = build_warning_frame(daily, threshold_pct)
    if len(data) < 50 or data["target"].nunique() < 2:
        return data, {
            "status": "insufficient_data",
            "reason": "Fewer than 50 labeled rows or only one target class.",
            "n": int(len(data)),
            "threshold_pct": threshold_pct,
        }
    split = int(len(data) * 0.8)
    train, test = data.iloc[:split], data.iloc[split:]
    if train["target"].nunique() < 2 or test["target"].nunique() < 2:
        return data, {
            "status": "insufficient_data",
            "reason": "Chronological train or holdout partition has only one target class.",
            "n": int(len(data)),
            "threshold_pct": threshold_pct,
        }

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)),
    ])
    x_train = train[feature_names].replace([np.inf, -np.inf], np.nan)
    x_test = test[feature_names].replace([np.inf, -np.inf], np.nan)
    usable_features = [name for name in feature_names if x_train[name].notna().any()]
    y_train = train["target"].astype(int)
    y_test = test["target"].astype(int)
    pipeline.fit(x_train[usable_features], y_train)
    probability = pipeline.predict_proba(x_test[usable_features])[:, 1]
    model_pred = probability >= 0.5
    # The fixed heuristic uses only the latest observed output change.
    baseline_pred = test["output_change_pct_1_report"].le(-5.0).fillna(False).to_numpy()
    metrics = {
        "status": "ok",
        "threshold_pct": threshold_pct,
        "split": "first 80% train, last 20% chronological holdout",
        "train_n": int(len(train)),
        "holdout_n": int(len(test)),
        "train_start": str(train["date"].min().date()),
        "train_end": str(train["date"].max().date()),
        "holdout_start": str(test["date"].min().date()),
        "holdout_end": str(test["date"].max().date()),
        "model": _metrics(y_test.to_numpy(), model_pred, probability),
        "momentum_baseline": _metrics(y_test.to_numpy(), baseline_pred),
        "average_lead_days": float(test["report_gap_to_target_days"].mean()),
        "feature_count": int(len(usable_features)),
        "decision_threshold": 0.5,
    }
    scored = data.copy()
    scored["predicted_probability"] = np.nan
    scored["model_alert"] = pd.NA
    scored.loc[test.index, "predicted_probability"] = probability
    scored.loc[test.index, "model_alert"] = model_pred.astype(int)
    scored["momentum_alert"] = pd.NA
    scored.loc[test.index, "momentum_alert"] = baseline_pred.astype(int)
    metrics["baseline_note"] = "Alert when previous one-report output change is at most -5%."
    return scored, metrics


def run_sensitivity(daily: pd.DataFrame, thresholds: tuple[float, ...] = (5.0, 10.0, 15.0)) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for threshold in thresholds:
        _, metrics = evaluate_threshold(daily, threshold)
        results[str(int(threshold))] = metrics
    return results
