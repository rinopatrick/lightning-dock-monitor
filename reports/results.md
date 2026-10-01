# Lightning Dock analysis results

## Diagnostic output events

473 output decline events of at least 10% within 7 days.

Strongest absolute Spearman association among rows with n >= 30: well::47-7::psi at 2 report step(s), rho=0.284, n=94, median span=2.0 days. This is an exploratory association, not evidence of causation.

## Early-warning model

The label is a net-to-grid output decline of at least 10% at the next valid report, if it arrives within seven days. Extreme output values are excluded from change targets and model fitting, but remain flagged in the profile.

On the chronological holdout (706 reports, 2024-07-14 to 2026-08-01), the logistic model had precision 13.4%, recall 70.0%, average precision 0.154, and 66.2 false alerts per 100 negative reports. The momentum baseline had precision 17.0%, recall 31.1%, and 22.2 false alerts per 100 negatives. Mean forecast horizon: 1.0 days.

Metrics and 5%, 10%, and 15% sensitivity results are in warning_metrics.json. Predictions are in warning_predictions.csv. The last 20% of labeled observations form a chronological holdout; the first 80% train logistic regression. The model uses a 0.5 probability cutoff; the baseline alerts after a one-report output drop of at least 5%.

This is a retrospective portfolio analysis, not an operational plant alert. Associations are descriptive and do not establish cause.
