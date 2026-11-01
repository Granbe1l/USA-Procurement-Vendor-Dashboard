import pandas as pd
import pytest
from concentration import compare_concentration


def test_sql_nets_adjustments_keeps_ties_and_separates_years():
    rows = [('NSF', 2024, 'a', 90), ('NSF', 2024, 'a', -50),
            ('NSF', 2024, 'b', 40), ('NSF', 2024, 'c', 20),
            ('NSF', 2024, 'd', -10), ('NSF', 2024, '', 200),
            ('NSF', 2025, 'a', 50), ('NRC', 2024, 'z', -10)]
    data = pd.DataFrame(rows, columns=['agency', 'fiscal_year', 'vendor_id', 'obligation_cents'])
    result = compare_concentration(data).set_index(['agency', 'fiscal_year'])
    row = result.loc[('NSF', 2024)]
    assert row.net_obligation_cents == 290
    assert row.missing_vendor_rows == 1
    assert row.positive_vendors == 3
    assert row.category_a_vendors == 2
    assert row.category_a_value_share == pytest.approx(.8)
    assert row.hhi == pytest.approx(3600)
    assert result.loc[('NSF', 2025)].hhi == 10000
    assert pd.isna(result.loc[('NRC', 2024)].hhi)


def test_sql_tie_crossing_boundary_stays_in_a():
    data = pd.DataFrame([('NSF', 2024, str(i), n) for i, n in enumerate([70, 15, 15])],
                        columns=['agency', 'fiscal_year', 'vendor_id', 'obligation_cents'])
    row = compare_concentration(data).iloc[0]
    assert row.category_a_vendors == 3
    assert row.category_a_value_share == 1
