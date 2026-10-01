from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .profile import DATE_COLUMN, MAX_REPORT_GAP_DAYS, OUTPUT_COLUMN, flag_extreme_output


def decline_events(daily: pd.DataFrame, threshold_pct: float = 10.0) -> pd.DataFrame:
    """Find output drops against the preceding valid report, within a 7-day gap."""
    frame = daily.copy()
    frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN], errors="coerce")
    frame[OUTPUT_COLUMN] = pd.to_numeric(frame[OUTPUT_COLUMN], errors="coerce")
    extreme, _ = flag_extreme_output(frame)
    frame = frame.loc[~extreme & frame[OUTPUT_COLUMN].gt(0)].sort_values(DATE_COLUMN)
    previous = frame[OUTPUT_COLUMN].shift(1)
    previous_date = frame[DATE_COLUMN].shift(1)
    gap = (frame[DATE_COLUMN] - previous_date).dt.days
    change = (frame[OUTPUT_COLUMN] / previous - 1.0) * 100.0
    mask = previous.notna() & gap.between(1, MAX_REPORT_GAP_DAYS) & change.le(-threshold_pct)
    result = frame.loc[mask, [DATE_COLUMN, OUTPUT_COLUMN, "source_report_count"]].copy()
    result["previous_date"] = previous_date.loc[mask]
    result["previous_output_kw"] = previous.loc[mask]
    result["gap_days"] = gap.loc[mask].astype(int)
    result["change_pct"] = change.loc[mask]
    result = result.rename(columns={DATE_COLUMN: "event_date", OUTPUT_COLUMN: "output_kw"})
    return result.reset_index(drop=True)


def _delta(series: pd.Series) -> pd.Series:
    prior = series.shift(1)
    diff = series - prior
    return diff.where(prior.abs() < 1e-9, diff / prior.abs() * 100.0)


def lag_associations(daily: pd.DataFrame, max_lag: int = 5) -> pd.DataFrame:
    """Compare per-well signal changes with later output changes over report lags."""
    frame = daily.copy().sort_values(DATE_COLUMN).reset_index(drop=True)
    frame[DATE_COLUMN] = pd.to_datetime(frame[DATE_COLUMN], errors="coerce")
    output = pd.to_numeric(frame[OUTPUT_COLUMN], errors="coerce")
    extreme, _ = flag_extreme_output(frame)
    valid_out = output.where(~extreme & output.gt(0))
    out_change = _delta(valid_out)
    out_gap = frame[DATE_COLUMN].diff().dt.days
    signals = [c for c in frame.columns if c.startswith("well::")]
    rows: list[dict[str, Any]] = []

    for signal in signals:
        values = pd.to_numeric(frame[signal], errors="coerce")
        signal_change = _delta(values)
        signal_gap = frame[DATE_COLUMN].diff().dt.days
        for lag in range(1, max_lag + 1):
            # A signal change ending at row i precedes the output change ending at i+lag.
            x = signal_change
            y = out_change.shift(-lag)
            needed = pd.DataFrame({
                "signal_change": x,
                "output_change": y,
                "signal_gap": signal_gap,
                "output_gap": out_gap.shift(-lag),
            }).dropna()
            needed = needed.loc[
                needed["signal_gap"].between(1, MAX_REPORT_GAP_DAYS)
                & needed["output_gap"].between(1, MAX_REPORT_GAP_DAYS)
            ]
            if len(needed) < 3 or needed["signal_change"].nunique() < 2 or needed["output_change"].nunique() < 2:
                rho, pvalue = np.nan, np.nan
            else:
                stat = spearmanr(needed["signal_change"], needed["output_change"])
                rho, pvalue = float(stat.statistic), float(stat.pvalue)
            rows.append({
                "signal": signal,
                "lag_report_steps": lag,
                "n": int(len(needed)),
                "median_signal_to_outcome_days": (
                    float((needed["signal_gap"] + needed["output_gap"]).median())
                    if not needed.empty else np.nan
                ),
                "spearman_rho": rho,
                "p_value_unadjusted": pvalue,
            })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["absolute_rho"] = result["spearman_rho"].abs()
        result = result.sort_values(
            ["lag_report_steps", "n", "absolute_rho"],
            ascending=[True, False, False],
            na_position="last",
        )
    return result


def summarize_associations(associations: pd.DataFrame) -> str:
    if associations.empty:
        return "No per-well association rows were available."
    eligible = associations.loc[associations["n"].ge(30) & associations["spearman_rho"].notna()]
    if eligible.empty:
        return "No associations had at least 30 paired observations; treat the diagnostic as underpowered."
    top = eligible.sort_values("absolute_rho", ascending=False).iloc[0]
    return (
        f"Strongest absolute Spearman association among rows with n >= 30: "
        f"{top['signal']} at {int(top['lag_report_steps'])} report step(s), "
        f"rho={top['spearman_rho']:.3f}, n={int(top['n'])}, "
        f"median span={top['median_signal_to_outcome_days']:.1f} days. "
        "This is an exploratory association, not evidence of causation."
    )
