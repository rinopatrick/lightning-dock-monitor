from __future__ import annotations
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
DATA = ROOT / "data" / "processed" / "daily_operations.csv"
OUTPUT = "net_to_grid_kw"

st.set_page_config(page_title="Lightning Dock Monitor", page_icon="⚡", layout="wide")
st.title("Lightning Dock | Well-to-Plant Monitor")
st.caption("Exploratory operations analytics for public geothermal field data")

if not DATA.exists():
    st.warning("Analysis artifacts are missing. Run python scripts/run_analysis.py first.")
    st.stop()

daily = pd.read_csv(DATA, parse_dates=["date"])
profile_path = REPORTS / "data_profile.json"
profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
metrics_path = REPORTS / "warning_metrics.json"
warning = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
events_path = REPORTS / "decline_events.csv"
events = pd.read_csv(events_path, parse_dates=["event_date"]) if events_path.exists() else pd.DataFrame()
assoc_path = REPORTS / "well_output_associations.csv"
associations = pd.read_csv(assoc_path) if assoc_path.exists() else pd.DataFrame()
pred_path = REPORTS / "warning_predictions.csv"
predictions = pd.read_csv(pred_path, parse_dates=["date"]) if pred_path.exists() else pd.DataFrame()

signals = [c for c in daily.columns if c.startswith("well::")]
wells = sorted({c.split("::")[1] for c in signals if len(c.split("::")) > 2})
signal_types = sorted({c.split("::")[-1] for c in signals})
well_fields = st.sidebar.selectbox("Well", wells, index=0 if wells else None)
signal_field = st.sidebar.selectbox("Signal", signal_types, index=0 if signal_types else None)
min_date = daily["date"].min().date()
max_date = daily["date"].max().date()
selected_range = st.sidebar.date_input(
    "Report period", value=(min_date, max_date), min_value=min_date, max_value=max_date
)
if isinstance(selected_range, (tuple, list)) and len(selected_range) == 2:
    start_date, end_date = selected_range
else:
    start_date = end_date = selected_range
start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date) + pd.Timedelta(days=1)
selected_signal = f"well::{well_fields}::{signal_field}" if well_fields and signal_field else None
show_extremes = st.sidebar.checkbox("Include extreme output readings", value=False)

def in_period(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame:
        return frame.iloc[0:0].copy()
    dates = pd.to_datetime(frame[column], errors="coerce")
    return frame.loc[dates.ge(start_ts) & dates.lt(end_ts)].copy()

period_daily = in_period(daily, "date")
period_events = in_period(events, "event_date")
period_predictions = in_period(predictions, "date") if not predictions.empty else pd.DataFrame()
cutoff = float(profile.get("outlier_cutoff_kw", float("inf")))
period_output = period_daily.loc[period_daily[OUTPUT].notna()].copy()
period_output["extreme_output"] = period_output[OUTPUT].abs().gt(cutoff)
if not show_extremes:
    period_output = period_output.loc[~period_output["extreme_output"]]

overview, diagnostic, early_warning = st.tabs(["Overview", "Diagnostics", "Early warning"])

with overview:
    intervals = period_daily["date"].sort_values().diff().dt.days.dropna()
    a, b, c, d = st.columns(4)
    a.metric("Report dates", f"{len(period_daily):,}")
    b.metric("Median report gap", f"{intervals.median():.0f} days" if not intervals.empty else "n/a")
    c.metric("Output median", f"{period_output[OUTPUT].median():,.0f} kW" if not period_output.empty else "n/a")
    d.metric("Extreme values flagged", f"{profile.get('extreme_output_count', 0):,}")
    line = go.Figure()
    line.add_trace(go.Scatter(x=period_output["date"], y=period_output[OUTPUT], mode="lines",
                              name="Net to grid (kW)", line={"color": "#34d399"}))
    line.update_layout(template="plotly_dark", title="Net electricity sent to grid",
                       xaxis_title="", yaxis_title="kW", hovermode="x unified")
    st.plotly_chart(line, use_container_width=True)
    coverage = []
    for name in signals:
        values = pd.to_numeric(period_daily[name], errors="coerce")
        coverage.append({"well": name.split("::")[1], "signal": name.split("::")[-1],
                         "reported": int(values.notna().sum()),
                         "coverage_pct": float(values.notna().mean() * 100) if len(values) else 0.0})
    coverage_frame = pd.DataFrame(coverage)
    if not coverage_frame.empty:
        coverage_frame = coverage_frame.sort_values("coverage_pct", ascending=False)
        st.subheader("Per-well report coverage")
        st.dataframe(coverage_frame, use_container_width=True, hide_index=True)
    st.caption(
        f"Source archive spans {profile.get('date_start')} to {profile.get('date_end')}; "
        f"{profile.get('excluded_rows', 0):,} source error/non-date rows excluded, "
        f"{profile.get('repeated_date_groups', 0):,} repeated-date groups median-aggregated."
    )

with diagnostic:
    if not selected_signal:
        st.info("No per-well signals were found.")
    else:
        signal_values = pd.to_numeric(period_daily[selected_signal], errors="coerce")
        observed = int(signal_values.notna().sum())
        coverage_pct = signal_values.notna().mean() * 100 if len(signal_values) else 0.0
        st.metric(f"{selected_signal} coverage", f"{observed:,} / {len(period_daily):,} reports",
                  f"{coverage_pct:.1f}%")
        chart = make_subplots(specs=[[{"secondary_y": True}]])
        chart.add_trace(go.Scatter(x=period_output["date"], y=period_output[OUTPUT], mode="lines",
                                   name="Net to grid (kW)", line={"color": "#34d399"}), secondary_y=False)
        chart.add_trace(go.Scatter(x=period_daily["date"], y=signal_values, mode="lines+markers",
                                   name=selected_signal), secondary_y=True)
        chart.update_layout(template="plotly_dark", title=f"Plant output and {selected_signal}",
                            hovermode="x unified", xaxis_title="")
        chart.update_yaxes(title_text="Net to grid (kW)", secondary_y=False)
        chart.update_yaxes(title_text=signal_field, secondary_y=True)
        st.plotly_chart(chart, use_container_width=True)

    st.subheader("Output decline events")
    if period_events.empty:
        st.info("No matching events in this period.")
    else:
        st.dataframe(period_events.sort_values("change_pct"), use_container_width=True, hide_index=True)

    st.subheader("Lag associations")
    if not associations.empty and selected_signal:
        filtered_assoc = associations.loc[associations["signal"].eq(selected_signal)].copy()
        if not filtered_assoc.empty:
            st.dataframe(filtered_assoc[["lag_report_steps", "n", "median_signal_to_outcome_days",
                                         "spearman_rho", "p_value_unadjusted"]],
                         use_container_width=True, hide_index=True)
            st.caption("Signal changes are compared with later output changes; adjacent gaps must be <=7 days. Correlation is not causation.")

with early_warning:
    primary = warning.get("primary", {})
    if primary.get("status") != "ok":
        st.info(primary.get("reason", "Run the pipeline to generate warning metrics."))
    else:
        model = primary["model"]
        baseline = primary["momentum_baseline"]
        a, b, c, d = st.columns(4)
        a.metric("Holdout reports", f"{primary.get('holdout_n', 0):,}")
        b.metric("Average precision", f"{model.get('average_precision', 0):.3f}")
        c.metric("Recall at 0.5", f"{model.get('recall', 0):.1%}")
        d.metric("False alerts / 100 negatives", f"{model.get('false_alarms_per_100', 0):.1f}")
        st.write(
            f"Holdout: {primary.get('holdout_start')} to {primary.get('holdout_end')}. "
            f"Baseline recall {baseline.get('recall', 0):.1%}, precision {baseline.get('precision', 0):.1%}. "
            f"Mean forecast horizon: {primary.get('average_lead_days', 0):.1f} days."
        )
        holdout = period_predictions.loc[period_predictions["predicted_probability"].notna()].copy() if not period_predictions.empty else pd.DataFrame()
        if not holdout.empty:
            holdout["model_alert"] = pd.to_numeric(holdout["model_alert"], errors="coerce").fillna(0).astype(int)
            holdout["target"] = pd.to_numeric(holdout["target"], errors="coerce").fillna(0).astype(int)
            holdout = holdout.sort_values("date")
            plot = go.Figure()
            plot.add_trace(go.Scatter(x=holdout["date"], y=holdout["predicted_probability"],
                                      mode="lines", name="Decline probability",
                                      line={"color": "#60a5fa"}))
            plot.add_trace(go.Scatter(x=holdout["date"], y=holdout["model_alert"],
                                      mode="markers", name="Model alert",
                                      marker={"color": "#f87171", "size": 7}, yaxis="y2"))
            plot.update_layout(template="plotly_dark", title="Chronological holdout predictions",
                               xaxis_title="", yaxis_title="Probability", yaxis={"range": [0, 1]},
                               yaxis2={"title": "Alert (0/1)", "overlaying": "y", "side": "right",
                                       "range": [-0.1, 1.1]}, hovermode="x unified")
            st.plotly_chart(plot, use_container_width=True)
            st.subheader("Evaluated predictions")
            shown = holdout.assign(
                actual_drop=holdout["target"].map({0: "No", 1: "Yes"}),
                predicted_alert=holdout["model_alert"].map({0: "No", 1: "Yes"}),
            )
            st.dataframe(shown[["date", "output_kw", "target_drop_pct", "actual_drop",
                                "predicted_probability", "predicted_alert"]],
                         use_container_width=True, hide_index=True)
    sensitivity = warning.get("threshold_sensitivity", {})
    if sensitivity:
        rows = []
        for threshold, result in sensitivity.items():
            model = result.get("model", {})
            rows.append({"decline threshold": f"{threshold}%", "status": result.get("status"),
                         "precision": model.get("precision"), "recall": model.get("recall"),
                         "F1": model.get("f1"), "average precision": model.get("average_precision")})
        st.subheader("Target-threshold sensitivity")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Retrospective one-report analysis only. Not a live plant safety or maintenance alert.")

with st.expander("Method and data limits"):
    st.markdown(
        "- Error rows are excluded; repeated report dates use numeric medians. Blank cells remain missing, not zero.\n"
        "- A warning target exists only if the next valid output report arrives within seven days.\n"
        "- Model features use current and prior report values; evaluation uses a chronological holdout.\n"
        "- Extreme output values are flagged and excluded from changes and model targets.\n"
        "- Well-output relationships are exploratory associations, not causal claims."
    )

st.markdown(
    "Source: [Lightning Dock Geothermal Field Data Package](https://catalog.data.gov/dataset/lightning-dock-geothermal-field-data-package-hidalgo-county-new-mexico), "
    "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)."
)
