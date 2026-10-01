from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from lightning_dock.diagnostics import decline_events, lag_associations, summarize_associations
from lightning_dock.io import download_archive, load_operations
from lightning_dock.profile import canonicalize_reports, profile_data, render_profile_markdown
from lightning_dock.warning import evaluate_threshold, run_sensitivity

def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser(description="Profile and analyze Lightning Dock operations.")
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--diagnostics-only", action="store_true")
    parser.add_argument("--warning-only", action="store_true")
    parser.add_argument("--event-threshold", type=float, default=10.0)
    args = parser.parse_args()
    raw_dir = PROJECT_ROOT / "data" / "raw"
    processed_dir = PROJECT_ROOT / "data" / "processed"
    reports_dir = PROJECT_ROOT / "reports"
    for path in (raw_dir, processed_dir, reports_dir):
        path.mkdir(parents=True, exist_ok=True)
    archive = raw_dir / "04_PRODUCTION_INJECTION_GENERATION.zip"
    if not archive.exists():
        download_archive(archive)
    raw, source_files = load_operations(archive)
    daily = canonicalize_reports(raw)
    daily_path = processed_dir / "daily_operations.csv"
    daily.to_csv(daily_path, index=False)
    profile = profile_data(raw, daily)
    profile["archive_members"] = source_files
    (reports_dir / "data_profile.md").write_text(render_profile_markdown(profile), encoding="utf-8")
    write_json(reports_dir / "data_profile.json", profile)
    print(f"Profiled {len(raw):,} raw rows into {len(daily):,} report dates.")
    if args.profile_only:
        print(f"Wrote {daily_path} and {reports_dir / 'data_profile.md'}")
        return
    run_diagnostics = not args.warning_only
    run_warning = not args.diagnostics_only
    event_summary = "Skipped."
    warning_summary = "Skipped."
    if run_diagnostics:
        events = decline_events(daily, args.event_threshold)
        associations = lag_associations(daily)
        events.to_csv(reports_dir / "decline_events.csv", index=False)
        associations.to_csv(reports_dir / "well_output_associations.csv", index=False)
        event_summary = f"{len(events):,} output decline events of at least {args.event_threshold:g}% within 7 days."
        event_summary += "\n\n" + summarize_associations(associations)
        print(event_summary)
    if run_warning:
        scored, primary = evaluate_threshold(daily, args.event_threshold)
        sensitivity = run_sensitivity(daily)
        scored.to_csv(reports_dir / "warning_predictions.csv", index=False)
        write_json(reports_dir / "warning_metrics.json", {"primary": primary, "threshold_sensitivity": sensitivity})
        print(json.dumps(primary, indent=2, default=str))
        if primary.get("status") == "ok":
            model = primary["model"]
            baseline = primary["momentum_baseline"]
            warning_summary = (
                f"On the chronological holdout ({primary['holdout_n']:,} reports, "
                f"{primary['holdout_start']} to {primary['holdout_end']}), the logistic model "
                f"had precision {model['precision']:.1%}, recall {model['recall']:.1%}, "
                f"average precision {model['average_precision']:.3f}, and "
                f"{model['false_alarms_per_100']:.1f} false alerts per 100 negative reports. "
                f"The momentum baseline had precision {baseline['precision']:.1%}, "
                f"recall {baseline['recall']:.1%}, and "
                f"{baseline['false_alarms_per_100']:.1f} false alerts per 100 negatives. "
                f"Mean forecast horizon: {primary['average_lead_days']:.1f} days."
            )
        else:
            warning_summary = f"Model status: {primary.get('status')}. {primary.get('reason', '')}"
    report = f"""# Lightning Dock analysis results

## Diagnostic output events

{event_summary}

## Early-warning model

The label is a net-to-grid output decline of at least {args.event_threshold:g}% at the next valid report, if it arrives within seven days. Extreme output values are excluded from change targets and model fitting, but remain flagged in the profile.

{warning_summary}

Metrics and 5%, 10%, and 15% sensitivity results are in warning_metrics.json. Predictions are in warning_predictions.csv. The last 20% of labeled observations form a chronological holdout; the first 80% train logistic regression. The model uses a 0.5 probability cutoff; the baseline alerts after a one-report output drop of at least 5%.

This is a retrospective portfolio analysis, not an operational plant alert. Associations are descriptive and do not establish cause.
"""
    (reports_dir / "results.md").write_text(report, encoding="utf-8")
    print(f"Results saved under {reports_dir}")

if __name__ == "__main__":
    main()
