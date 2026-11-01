# Screenshots to add

Capture the **review-branch** app (`fix/official-data`) with its verified bundled snapshot before merging into `main`. The existing public Streamlit URL still points to production and must not be used as evidence of the review-branch changes. Do not use fixture data or fabricated screenshots. Run the review branch locally or create a separate Streamlit Community Cloud preview deployment selecting `fix/official-data` and `app.py`; do not change the existing production deployment. Record the snapshot retrieval date and filter state alongside each screenshot. Screenshots are captured automatically from the verified official snapshot in GitHub Actions. The owner reviews and approves final images before they are committed to README.

1. `overview.png`: desktop Overview, all filters cleared; include the title, KPI cards, Key Findings and Pareto/distribution. The case-study expander can remain closed.
2. `concentration.png`: Concentration & SQL, select Concentration; show formatted agency-year values and expand SQL behind this chart.
3. `fiscal-year-comparison.png`: both FYs selected, all agencies; show delta KPIs, grouped bars and rank-change table (a second capture is fine if needed).

Before capture, verify the browser displays the official retrieval timestamp and that KPI/SQL values match `data/processed/findings.md`. Check desktop and mobile for clipped labels, overflowing tables, filter controls and chart tooltips. Record viewport dimensions and any discrepancies. After placing the genuine screenshots here, add these exact links in the root README:

```markdown
![Overview with verified source data](docs/images/overview.png)
![Agency-year concentration and SQL](docs/images/concentration.png)
![Fiscal-year comparison](docs/images/fiscal-year-comparison.png)
```

The older `docs/overview-empty-desktop.png` and `docs/overview-empty-mobile.png` remain historical empty-state references and are not populated-data evidence.

## Automated review evidence (2026-11-01)

[GitHub Actions screenshot run #6](https://github.com/Granbe1l/USA-Federal-Procurement-Vendor-Dashboard/actions/runs/41260276792) succeeded. Its `official-snapshot-visual-review` artifact contains desktop Overview, ABC, Fiscal-Year Comparison, Concentration & SQL, and mobile Overview PNG segments plus viewport/scroll metadata JSON. The artifact is not yet an embedded README screenshot.

**Visual inspection:** desktop Overview's first segment shows title, verified source timestamp, KPI cards and three Key Findings clearly. ABC and Fiscal-Year first segments show their main visualizations. However, subsequent Overview segments do not yet establish that the entire Pareto and distribution charts are captured; do not label them full-page screenshots. The capture metadata currently records `snapshot: null` because the source timestamp field is named differently in the metadata; this does not imply missing data, as the app itself displays the timestamp. Do not publish an image as complete until the chart and labels are fully visible.

**Next action:** verify Streamlit's actual scroll element and its effective `scrollTop` after each scroll, capture complete chart views, then select and commit genuine images. The existing public deployment remains unchanged.
