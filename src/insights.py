"""Descriptive findings generated from query outputs; no fixed dataset findings."""
import pandas as pd


def build_findings(concentration, annual):
    findings = []
    positive = concentration.dropna(subset=['hhi', 'top_vendor_share'])
    if not positive.empty:
        row = positive.sort_values(['top_vendor_share', 'agency', 'fiscal_year'], ascending=[False, True, True]).iloc[0]
        findings.append((
            f'{row.agency}, FY{int(row.fiscal_year)}: one recipient accounts for {row.top_vendor_share:.1%} of positive-net vendor value.',
            'Review the underlying awards and adjustments for that recipient before interpreting dependence.',
            '04_concentration_hhi.sql'))
        for year in sorted(positive.fiscal_year.unique(), reverse=True):
            current = positive.loc[positive.fiscal_year.eq(year)]
            if len(current) >= 2:
                low = current.sort_values(['hhi', 'agency']).iloc[0]
                high = current.sort_values(['hhi', 'agency']).iloc[-1]
                findings.append((
                    f'FY{int(year)}: {high.agency} HHI {high.hhi:,.0f} versus {low.agency} {low.hhi:,.0f} (gap {high.hhi - low.hhi:,.0f} points).',
                    'Compare contract mix and agency missions; HHI is not a performance or risk score.',
                    '04_concentration_hhi.sql'))
                break
    combined = annual.loc[annual.scope.eq('combined') & annual.previous_year.notna()].sort_values('fiscal_year')
    if not combined.empty:
        row = combined.iloc[-1]
        percent = f'{row.change_share:+.1%}' if pd.notna(row.change_share) else 'percentage undefined: prior total is zero'
        findings.append((
            f'Combined signed obligations changed by {row.change_usd:+,.2f} USD ({percent}), FY{int(row.previous_year)} to FY{int(row.fiscal_year)}.',
            'Inspect modifications and agency-level changes; two years do not establish a trend.',
            '06_fy_comparison.sql'))
    return findings
