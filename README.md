# Lightning Dock Well-to-Plant Monitor

An operations analytics portfolio project using public geothermal field reports. It profiles data quality, compares well-signal changes with later plant-output changes, and evaluates a next-report output-decline warning model.

## Data source and attribution

- Dataset: [Lightning Dock Geothermal Field Data Package](https://catalog.data.gov/dataset/lightning-dock-geothermal-field-data-package-hidalgo-county-new-mexico)
- Direct archive: https://gdr.openei.org/files/1856/04_PRODUCTION_INJECTION_GENERATION.zip
- License: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
- Table: production_injection_generation_reports_daily.csv
- Plant outcome: net_to_grid_kw, electricity sent to the grid in kW, as defined by the source guide.

Only the production/injection/generation archive and its column guide are used. The archive contains 6,850 source rows. Rows with a non-empty error value are excluded. Empty cells mean not reported, not zero. The guide describes a file identifier, but the CSV header has no file field, so repeated calendar dates are consolidated with per-column medians; report counts and conflicting values are retained.

## What it does

1. Profiles source coverage, error categories, missingness, duplicate dates, output gaps, and extreme values.
2. Flags output drops of at least 10% between valid reports no more than seven days apart.
3. Scans per-well signal changes against later output changes over one to five report steps. It reports sample count, Spearman correlation, and time span, without causal claims.
4. Trains an interpretable logistic-regression model to flag a decline of at least 10% at the next valid output report, if that report arrives within seven days.
5. Holds out the latest 20% of labeled observations chronologically and compares the model with a fixed momentum rule.
6. Repeats the warning evaluation at 5%, 10%, and 15% decline thresholds.
7. Displays source coverage, time-filtered well/output timelines, diagnostic events, and evaluated holdout predictions in Streamlit.

Extreme output values are flagged using an explicit full-series rule: absolute output above 10 times the absolute 99th percentile. They remain in the data profile but are excluded from change targets and model fitting. No values are silently clipped.

## Findings from this run

- The 6,850-row source reduced to 4,299 dated daily-report rows and 3,740 unique report dates after excluding error rows and median-aggregating repeats.
- There are 3,582 report dates with net-to-grid readings; the median interval is one day. Three extreme output readings were flagged.
- The 10% decline scan found 473 report-to-report drops within seven days.
- The strongest adequately covered well-signal association was well 47-7 pressure at two report steps: Spearman rho 0.284 from 94 paired observations, with a median span of two days. This is exploratory and does not show that pressure changes caused output changes.
- On the last 20% chronological holdout (706 reports, July 2024 to August 2026), the logistic model reached 70.0% recall, 13.4% precision, and 0.154 average precision for the 10% decline target. It produced 66.2 false alerts per 100 negative reports.
- The momentum baseline reached 31.1% recall and 17.0% precision, with 22.2 false alerts per 100 negative reports.

The model catches more declines on this holdout but raises many more false alerts. Average lead is about one day because the target is the next available report. This is a retrospective experiment, not a validated plant alert or maintenance recommendation. See reports/results.md and reports/warning_metrics.json for complete metrics and threshold sensitivity.

## Run it

Python 3.11 or newer is recommended.

~~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/download_data.py
python scripts/run_analysis.py
streamlit run app.py
~~~~

run_analysis.py downloads the source archive automatically if it is absent. Use --profile-only, --diagnostics-only, or --warning-only to run a subset. The raw archive, local environment, and processed CSVs are gitignored; generated reports remain available for review.

## Output files

- reports/data_profile.md and reports/data_profile.json
- reports/decline_events.csv
- reports/well_output_associations.csv
- reports/warning_metrics.json
- reports/warning_predictions.csv
- reports/results.md
- data/processed/daily_operations.csv

## Limitations

- Report intervals are irregular. Adjacent changes with gaps over seven days are not compared.
- Per-well readings are sparse; each association includes its actual paired sample size.
- The data package is operational reporting, not a controlled experiment.
- Holdout metrics depend on the time boundary and target definition; they do not establish deployment readiness.
