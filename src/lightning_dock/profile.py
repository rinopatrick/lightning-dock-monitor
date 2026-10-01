from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

OUTPUT_COLUMN = "net_to_grid_kw"
DATE_COLUMN = "date"
ERROR_COLUMN = "error"
MAX_REPORT_GAP_DAYS = 7


def canonicalize_reports(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep dated daily plant reports and median-aggregate repeated dates."""
    required = {DATE_COLUMN, ERROR_COLUMN, OUTPUT_COLUMN}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Required source columns are missing: {sorted(missing)}")

    dated = raw.copy()
    dated[DATE_COLUMN] = pd.to_datetime(dated[DATE_COLUMN], errors="coerce")
    errors = dated[ERROR_COLUMN].fillna("").astype(str).str.strip()
    eligible = dated.loc[errors.eq("") & dated[DATE_COLUMN].notna()].copy()
    if eligible.empty:
        raise ValueError("No dated daily plant reports remain after filtering error rows.")

    numeric_columns = [col for col in eligible.columns if col not in {DATE_COLUMN, ERROR_COLUMN}]
    for col in numeric_columns:
        eligible[col] = pd.to_numeric(eligible[col], errors="coerce")
    grouped = eligible.groupby(DATE_COLUMN, sort=True)[numeric_columns]
    daily = grouped.median(numeric_only=True)
    daily.index.name = DATE_COLUMN
    daily = daily.reset_index()
    counts = grouped.size().rename("source_report_count").reset_index()
    conflicts = grouped.nunique(dropna=True).gt(1).sum(axis=1).rename(
        "duplicate_conflict_columns"
    ).reset_index()
    daily = daily.merge(counts, on=DATE_COLUMN, how="left")
    daily = daily.merge(conflicts, on=DATE_COLUMN, how="left")
    daily["duplicate_conflict_present"] = daily["duplicate_conflict_columns"].gt(0)
    return daily.sort_values(DATE_COLUMN).reset_index(drop=True)


def outlier_cutoff(values: pd.Series) -> float:
    """Flag values over ten times the full-series absolute 99th percentile."""
    numeric = pd.to_numeric(values, errors="coerce").dropna().abs()
    if numeric.empty:
        return float("inf")
    q99 = float(numeric.quantile(0.99))
    return q99 * 10.0 if q99 > 0 else float("inf")


def flag_extreme_output(
    daily: pd.DataFrame, output_column: str = OUTPUT_COLUMN
) -> tuple[pd.Series, float]:
    cutoff = outlier_cutoff(daily[output_column])
    values = pd.to_numeric(daily[output_column], errors="coerce")
    return values.abs().gt(cutoff).fillna(False), cutoff


def profile_data(raw: pd.DataFrame, daily: pd.DataFrame) -> dict[str, Any]:
    dates = pd.to_datetime(daily[DATE_COLUMN], errors="coerce")
    output = pd.to_numeric(daily[OUTPUT_COLUMN], errors="coerce")
    output_dates = dates[output.notna()].dropna().sort_values()
    gaps = output_dates.diff().dt.days.dropna()
    raw_dates = pd.to_datetime(raw[DATE_COLUMN], errors="coerce")
    errors = raw[ERROR_COLUMN].fillna("").astype(str).str.strip()
    daily_rows = errors.eq("") & raw_dates.notna()
    repeated = daily.loc[daily["source_report_count"].gt(1)]
    extreme, cutoff = flag_extreme_output(daily)
    error_counts = Counter(value if value else "(blank)" for value in errors)
    value_columns = [c for c in raw.columns if c not in {DATE_COLUMN, ERROR_COLUMN}]
    missing = {c: round(float(raw[c].isna().mean() * 100), 2) for c in value_columns}

    return {
        "raw_rows": int(len(raw)),
        "raw_columns": int(len(raw.columns)),
        "daily_source_rows": int(daily_rows.sum()),
        "excluded_rows": int(len(raw) - daily_rows.sum()),
        "error_counts": dict(error_counts),
        "date_start": str(dates.min().date()) if dates.notna().any() else "",
        "date_end": str(dates.max().date()) if dates.notna().any() else "",
        "unique_report_dates": int(dates.nunique()),
        "repeated_date_groups": int(len(repeated)),
        "extra_duplicate_rows": int((repeated["source_report_count"] - 1).sum()),
        "duplicate_conflict_presents": int(daily["duplicate_conflict_present"].sum()),
        "file_identifier_present": "file" in raw.columns,
        "output_dates": int(output.notna().sum()),
        "output_start": str(output_dates.min().date()) if not output_dates.empty else "",
        "output_end": str(output_dates.max().date()) if not output_dates.empty else "",
        "median_output_gap_days": float(gaps.median()) if not gaps.empty else None,
        "max_output_gap_days": int(gaps.max()) if not gaps.empty else None,
        "gaps_over_seven_days": int(gaps.gt(MAX_REPORT_GAP_DAYS).sum()),
        "output_min_kw": float(output.min()) if output.notna().any() else None,
        "output_median_kw": float(output.median()) if output.notna().any() else None,
        "output_max_kw": float(output.max()) if output.notna().any() else None,
        "outlier_cutoff_kw": float(cutoff),
        "extreme_output_count": int(extreme.sum()),
        "output_missing_pct": round(float(raw[OUTPUT_COLUMN].isna().mean() * 100), 2),
        "missing_pct": missing,
        "well_signal_columns": [c for c in raw.columns if c.startswith("well::")],
    }


def render_profile_markdown(profile: dict[str, Any]) -> str:
    errors = "\n".join(
        f"- {name}: {count}" for name, count in profile["error_counts"].items()
    )
    top_missing = sorted(
        profile["missing_pct"].items(), key=lambda item: item[1], reverse=True
    )[:10]
    missing_rows = "\n".join(
        f"| {name} | {pct:.2f}% |" for name, pct in top_missing
    )
    file_note = (
        "The CSV includes the file identifier described by the guide."
        if profile["file_identifier_present"]
        else "The guide describes a file identifier, but the CSV header has no file column; repeated dates are grouped by date."
    )
    return f"""# Lightning Dock data profile

## Source

Lightning Dock Geothermal Field Data Package, public access, CC BY 4.0.
Source page: https://catalog.data.gov/dataset/lightning-dock-geothermal-field-data-package-hidalgo-county-new-mexico

Operations table: production_injection_generation_reports_daily.csv.
Output measure: net_to_grid_kw, electricity sent to the grid, in kW.

## Coverage and row handling

- Raw table: {profile["raw_rows"]:,} rows x {profile["raw_columns"]} columns.
- Dated daily-report rows retained before date aggregation: {profile["daily_source_rows"]:,}.
- Rows excluded because they are error reports or have no usable date: {profile["excluded_rows"]:,}.
- Canonical report dates: {profile["unique_report_dates"]:,}, from {profile["date_start"]} to {profile["date_end"]}.
- Repeated-date groups: {profile["repeated_date_groups"]:,}; extra rows: {profile["extra_duplicate_rows"]:,}.
- Repeated dates with conflicting numeric columns: {profile["duplicate_conflict_presents"]:,}.
- {file_note}
- Empty cells remain missing, not zero. Repeated dates use the per-column median; report count and conflicting-column count are retained.

## Output coverage

- Valid net-to-grid readings after grouping: {profile["output_dates"]:,}, from {profile["output_start"]} to {profile["output_end"]}.
- Median interval between output dates: {profile["median_output_gap_days"]} days.
- Largest interval: {profile["max_output_gap_days"]} days; intervals over seven days: {profile["gaps_over_seven_days"]}.
- Output range: {profile["output_min_kw"]} to {profile["output_max_kw"]} kW; median: {profile["output_median_kw"]} kW.
- Extreme output values are flagged when absolute output exceeds 10 times the full-series absolute 99th percentile. This is a descriptive flag, not clipping.
- Flag threshold: {profile["outlier_cutoff_kw"]:.2f} kW; flagged values: {profile["extreme_output_count"]}.

## Source error categories

{errors}

## Highest-missing source columns

| Column | Missing |
| --- | ---: |
{missing_rows}

The source has {len(profile["well_signal_columns"])} per-well signal columns. The analysis uses actual report dates and does not interpolate across long gaps.
"""
