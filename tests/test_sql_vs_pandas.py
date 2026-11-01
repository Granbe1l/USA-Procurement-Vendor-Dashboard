"""DuckDB must match the unchanged pandas implementation, including edge cases."""
import json
from pathlib import Path

import pandas as pd
import pytest

from procurement import analyze, clean_transactions, load_data
from concentration import compare_concentration
from src.db import FILES, query_frame, run_sql_file

NSF = 'National Science Foundation'
NRC = 'Nuclear Regulatory Commission'


def transaction(i, vendor, amount, agency=NSF, date='2024-01-01', name=None):
    return dict(transaction_id=f't{i}', vendor_id=vendor, vendor_name=name or f'Vendor {vendor}',
                award_id=f'a{i}', action_date=date, agency=agency, state='NY', award_type='D',
                obligation=str(amount))


@pytest.fixture
def population():
    rows = [transaction(1, '001', '90'), transaction(2, '001', '-10'),
            transaction(3, '002', '10', name='SAME NAME'),
            transaction(4, '003', '6', name='SAME NAME'),
            transaction(5, '004', '4'), transaction(6, '005', '-5'),
            transaction(7, '006', '0'), transaction(8, '', '7'),
            transaction(9, '001', '2', NRC, '2024-10-01'),
            transaction(10, 'new', '8', NSF, '2025-01-01'),
            transaction(11, '001', '-2', NSF, '2025-01-01')]
    return clean_transactions(pd.DataFrame(rows))[0]


def assert_parity(frame):
    sql = query_frame(frame, '02_abc_classification.sql')
    comparisons = [(sql.loc[sql.scope.eq('combined')], analyze(frame))]
    for agency in frame.agency.unique():
        comparisons.append((sql.loc[sql.scope.eq('agency') & sql.agency.eq(agency)],
                            analyze(frame, agencies=[agency])))
    for actual, expected in comparisons:
        actual = actual.sort_values('vendor_id').set_index('vendor_id')
        expected = expected['vendors'].sort_values('vendor_id').set_index('vendor_id')
        assert actual.index.tolist() == expected.index.tolist()
        assert actual.category.to_dict() == expected.category.to_dict()
        assert actual.vendor_name.to_dict() == expected.vendor_name.to_dict()
        assert actual.net_obligations.tolist() == pytest.approx(expected.net_obligations.tolist(), abs=.01)
        for column in ['share', 'cumulative_share']:
            assert actual[column].isna().tolist() == expected[column].isna().tolist()
            valid = actual[column].notna()
            assert actual.loc[valid, column].tolist() == pytest.approx(expected.loc[valid, column].astype(float).tolist())


def test_vendor_totals_classes_and_fiscal_year_totals(population):
    for frame in [population, population.sample(frac=1, random_state=17),
                  population.loc[population.fiscal_year.eq(2024)], population.iloc[:0]]:
        assert_parity(frame)
    totals = query_frame(population, '01_vendor_totals.sql')
    for (agency, year), group in population.groupby(['agency', 'fiscal_year']):
        expected = analyze(group)['vendors'].set_index('vendor_id').net_obligations.to_dict()
        actual = totals.loc[totals.agency.eq(agency) & totals.fiscal_year.eq(year)].set_index('vendor_id').net_obligations.to_dict()
        assert actual == pytest.approx(expected, abs=.01)
    yearly = query_frame(population, '06_fy_comparison.sql')
    actual = yearly.loc[yearly.scope.eq('combined')].set_index('fiscal_year').net_obligations.to_dict()
    expected = analyze(population)['trends'].set_index('fiscal_year').net_obligations.to_dict()
    assert actual == pytest.approx(expected, abs=.01)
    for agency in population.agency.unique():
        actual = yearly.loc[yearly.scope.eq('agency') & yearly.agency.eq(agency)].set_index('fiscal_year').net_obligations.to_dict()
        expected = analyze(population, agencies=[agency])['trends'].set_index('fiscal_year').net_obligations.to_dict()
        assert actual == pytest.approx(expected, abs=.01)


@pytest.mark.parametrize('amounts', [[80, 15, 5], [50, 20, 20, 8, 2], [70, 15, 15],
                                    [99, 1], [100], [0, -5], ['.10', '.20', '-.30'],
                                    ['8000000000000', '1500000000000', '500000000000']])
def test_exact_boundaries_ties_nonpositive_and_large_values(amounts):
    # Leading zeroes are explicit because the source money parser intentionally rejects '.10'.
    amounts = ['0' + x if isinstance(x, str) and x.startswith('.') else
               '-0' + x[1:] if isinstance(x, str) and x.startswith('-.') else x for x in amounts]
    frame = clean_transactions(pd.DataFrame([transaction(i, f'{i:03}', n) for i, n in enumerate(amounts)]))[0]
    assert_parity(frame)


def test_hhi_top_shares_match_pandas_and_legacy_case_study(population):
    sql = query_frame(population, '04_concentration_hhi.sql').set_index(['agency', 'fiscal_year'])
    legacy = compare_concentration(population).set_index(['agency', 'fiscal_year'])
    for column in legacy.columns:
        assert sql[column].isna().tolist() == legacy[column].isna().tolist()
        assert sql[column].dropna().tolist() == pytest.approx(legacy[column].dropna().tolist())
    for keys, group in population.groupby(['agency', 'fiscal_year']):
        expected = analyze(group)
        positives = expected['vendors'].loc[lambda v: v.net_obligations.gt(0)]
        row = sql.loc[keys]
        assert row.net_obligation_cents / 100 == pytest.approx(expected['kpi']['net_obligations'], abs=.01)
        if len(positives):
            shares = positives.share.astype(float)
            assert row.hhi == pytest.approx(10000 * (shares ** 2).sum())
            assert row.top_vendor_share == pytest.approx(shares.iloc[0])
            assert row.top_10_share == pytest.approx(shares.head(10).sum())
            assert row.category_a_vendors == int(positives.category.eq('A').sum())
        else:
            assert pd.isna(row.hhi)


def test_summary_matches_pandas_including_unclassified(population):
    sql = query_frame(population, '03_abc_summary.sql')
    actual = sql.loc[sql.scope.eq('combined')].set_index('category')
    expected = analyze(population)['distribution'].set_index('category')
    for column in expected.columns:
        assert actual[column].isna().tolist() == expected[column].isna().tolist()
        assert actual[column].dropna().tolist() == pytest.approx(expected[column].dropna().tolist())


def test_year_changes_overlap_and_rank_changes(population):
    annual = query_frame(population, '06_fy_comparison.sql')
    row = annual.loc[annual.scope.eq('combined') & annual.fiscal_year.eq(2025)].iloc[0]
    old = set(population.loc[population.fiscal_year.eq(2024) & population.vendor_id.ne(''), 'vendor_id'])
    new = set(population.loc[population.fiscal_year.eq(2025) & population.vendor_id.ne(''), 'vendor_id'])
    assert row.new_vendors == len(new - old)
    assert row.dropped_vendors == len(old - new)
    old_total = analyze(population, years=[2024])['kpi']['net_obligations']
    new_total = analyze(population, years=[2025])['kpi']['net_obligations']
    assert row.change_usd == pytest.approx(new_total - old_total)
    assert row.change_share == pytest.approx((new_total - old_total) / old_total)
    ranks = query_frame(population, '06_vendor_rank_changes.sql')
    ranks = ranks.loc[ranks.scope.eq('combined')].set_index('vendor_id')
    assert ranks.loc['001'].previous_rank == 1
    assert ranks.loc['001'].current_rank == 2
    assert pd.isna(ranks.loc['new'].previous_rank)
    overlaps = query_frame(population, '07_vendor_name_overlap.sql')
    assert overlaps.iloc[0].normalized_name == 'SAME NAME'
    assert overlaps.iloc[0].vendor_ids == '002, 003'
    zero = population.copy()
    zero.loc[zero.fiscal_year.eq(2024), 'obligation_cents'] = 0
    result = query_frame(zero, '06_fy_comparison.sql')
    assert result.loc[result.scope.eq('combined') & result.fiscal_year.eq(2025), 'change_share'].isna().all()


@pytest.mark.parametrize('suffix', ['parquet', 'csv.gz'])
def test_cached_file_runner_filters_and_preserves_string_ids(population, tmp_path, suffix):
    path = tmp_path / ('transactions.' + suffix)
    if suffix == 'parquet':
        population.to_parquet(path, index=False)
    else:
        population.to_csv(path, index=False)
    filters = (('fiscal_year', (2024,)), ('agency', (NSF,)))
    actual = run_sql_file('02_abc_classification.sql', data_path=path, filters=filters)
    actual = actual.loc[actual.scope.eq('combined')]
    expected = analyze(population, years=[2024], agencies=[NSF])['vendors']
    assert actual.set_index('vendor_id').category.to_dict() == expected.set_index('vendor_id').category.to_dict()
    assert '001' in actual.vendor_id.tolist()
    assert run_sql_file('04_concentration_hhi.sql', data_path=path, filters=(('agency', ()),)).empty
    for name in FILES:
        run_sql_file(name, data_path=path)
    with pytest.raises(ValueError):
        run_sql_file('../app.py', data_path=path)
    with pytest.raises(ValueError):
        run_sql_file('01_vendor_totals.sql', data_path=path, filters=(('unknown', ('x',)),))
    assert not list(tmp_path.glob('*.db'))


def test_top_ten_uses_ten_vendors_and_excludes_nonpositive():
    frame = clean_transactions(pd.DataFrame([transaction(i, f'V{i:02}', 20 - i) for i in range(22)]))[0]
    row = query_frame(frame, '04_concentration_hhi.sql').iloc[0]
    shares = analyze(frame)['vendors'].loc[lambda x: x.net_obligations.gt(0), 'share'].astype(float)
    assert row.top_10_share == pytest.approx(shares.head(10).sum())
    assert row.top_10_share < 1
    assert row.hhi == pytest.approx(10000 * (shares ** 2).sum())


def test_labels_formats_and_insights_do_not_mutate_calculations(population):
    from src.presentation import display_frame, vendor_labels
    from src.insights import build_findings
    original = analyze(population)['vendors']
    preserved = original.copy(deep=True)
    shown = display_frame(original)
    pd.testing.assert_frame_equal(original, preserved)
    assert 'net_cents' not in shown
    assert shown.loc[original.category.eq('Unclassified'), 'Share of positive value'].eq('—').all()
    assert shown.loc[original.vendor_id.eq('001'), 'Net obligations (USD)'].iloc[0] == '$80.00'
    labels = vendor_labels(original)
    assert labels['002'] != labels['003']
    assert labels['002'].endswith('002')
    concentration = query_frame(population, '04_concentration_hhi.sql')
    annual = query_frame(population, '06_fy_comparison.sql')
    findings = build_findings(concentration, annual)
    assert len(findings) == 3
    assert all(source in FILES for _, _, source in findings)
    filtered = population.loc[population.fiscal_year.eq(2024)]
    findings = build_findings(query_frame(filtered, '04_concentration_hhi.sql'),
                              query_frame(filtered, '06_fy_comparison.sql'))
    assert all('06_fy_comparison' not in source for _, _, source in findings)


@pytest.mark.parametrize('empty', [False, True])
def test_summary_has_explicit_zero_classes_without_identified_vendors(population, empty):
    frame = population.iloc[:0].copy() if empty else population.loc[population.vendor_id.eq('')].copy()
    result = query_frame(frame, '03_abc_summary.sql')
    actual = result.loc[result.scope.eq('combined')].set_index('category')
    expected = analyze(frame)['distribution'].set_index('category')
    assert actual.vendor_count.to_dict() == expected.vendor_count.to_dict()
    assert actual.value.to_dict() == expected.value.to_dict()
    assert actual.vendor_share.isna().all()
    assert actual.value_share.isna().all()
