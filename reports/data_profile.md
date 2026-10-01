# Lightning Dock data profile

## Source

Lightning Dock Geothermal Field Data Package, public access, CC BY 4.0.
Source page: https://catalog.data.gov/dataset/lightning-dock-geothermal-field-data-package-hidalgo-county-new-mexico

Operations table: production_injection_generation_reports_daily.csv.
Output measure: net_to_grid_kw, electricity sent to the grid, in kW.

## Coverage and row handling

- Raw table: 6,850 rows x 70 columns.
- Dated daily-report rows retained before date aggregation: 4,299.
- Rows excluded because they are error reports or have no usable date: 2,551.
- Canonical report dates: 3,740, from 2015-12-08 to 2026-08-03.
- Repeated-date groups: 555; extra rows: 559.
- Repeated dates with conflicting numeric columns: 172.
- The guide describes a file identifier, but the CSV header has no file column; repeated dates are grouped by date.
- Empty cells remain missing, not zero. Repeated dates use the per-column median; report count and conflicting-column count are retained.

## Output coverage

- Valid net-to-grid readings after grouping: 3,582, from 2015-12-15 to 2026-08-02.
- Median interval between output dates: 1.0 days.
- Largest interval: 152 days; intervals over seven days: 6.
- Output range: -1574.087926 to 108741818.1818182 kW; median: 4570.602321360753 kW.
- Extreme output values are flagged when absolute output exceeds 10 times the full-series absolute 99th percentile. This is a descriptive flag, not clipping.
- Flag threshold: 106000.00 kW; flagged values: 3.

## Source error categories

- not a daily plant report: 1709
- no DATA COLLECTION sheet: 842
- (blank): 4299

## Highest-missing source columns

| Column | Missing |
| --- | ---: |
| well::47-7::flow | 98.45% |
| well::47-7::psi | 98.44% |
| well::47-7::temp | 98.42% |
| well::47-7::hrs | 98.28% |
| well::63-7::flow | 98.20% |
| well::55-7::psi | 98.12% |
| well::55-7::flow | 98.03% |
| well::55-7::temp | 98.01% |
| well::63-7::temp | 94.20% |
| well::63-7::hrs | 94.16% |

The source has 56 per-well signal columns. The analysis uses actual report dates and does not interpolate across long gaps.
