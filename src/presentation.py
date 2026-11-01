"""Display-only copies; never change the data used for calculations or exports."""
import pandas as pd

LABELS = {
    'agency': 'Agency', 'scope': 'Scope', 'fiscal_year': 'Fiscal year', 'previous_year': 'Previous FY',
    'vendor_id': 'Recipient UEI', 'vendor_name': 'Vendor', 'category': 'ABC class',
    'net_obligations': 'Net obligations (USD)', 'positive_vendors': 'Positive-net vendors',
    'category_a_vendors': 'Category A vendors', 'category_a_value_share': 'Category A share of value',
    'top_vendor_share': 'Top vendor share', 'top_10_share': 'Top 10 share', 'hhi': 'HHI (0–10,000)',
    'vendor_count': 'Vendors', 'vendor_share': 'Share of vendor count', 'value': 'Net value (USD)',
    'value_share': 'Share of positive value', 'share': 'Share of positive value',
    'cumulative_share': 'Cumulative share', 'transactions': 'Transactions',
    'transaction_id': 'Transaction ID', 'award_id': 'Award ID', 'action_date': 'Action date',
    'state': 'Recipient state', 'recipient_state': 'Recipient state', 'award_type': 'Award type',
    'obligation': 'Obligation (USD)', 'change_usd': 'Change (USD)', 'change_share': 'Change (%)',
    'new_vendors': 'New recipients', 'dropped_vendors': 'Dropped recipients',
    'previous_rank': 'Previous rank', 'current_rank': 'Current rank', 'rank_improvement': 'Rank improvement',
    'previous_net_obligations': 'Previous net (USD)', 'current_net_obligations': 'Current net (USD)',
    'normalized_name': 'Shared normalized name', 'distinct_ueis': 'Distinct UEIs', 'vendor_ids': 'Recipient UEIs',
}
MONEY = {'net_obligations', 'value', 'obligation', 'change_usd', 'previous_net_obligations', 'current_net_obligations'}
SHARES = {'vendor_share', 'value_share', 'share', 'cumulative_share', 'category_a_value_share',
          'top_vendor_share', 'top_10_share', 'change_share'}
INTEGERS = {'fiscal_year', 'previous_year', 'positive_vendors', 'category_a_vendors', 'vendor_count',
            'transactions', 'new_vendors', 'dropped_vendors', 'previous_rank', 'current_rank',
            'rank_improvement', 'distinct_ueis'}


def display_frame(frame, columns=None):
    columns = columns or [c for c in frame.columns if c in LABELS]
    shown = frame[columns].copy()
    for column in columns:
        def render(value):
            if pd.isna(value):
                return '—'
            if column in MONEY:
                return f'-${abs(float(value)):,.2f}' if value < 0 else f'${float(value):,.2f}'
            if column in SHARES:
                return f'{float(value):.1%}'
            if column == 'hhi':
                return f'{float(value):,.0f}'
            if column in INTEGERS:
                return str(int(value)) if column in {'fiscal_year', 'previous_year'} else f'{int(value):,}'
            return str(value)
        shown[column] = shown[column].map(render)
    return shown.rename(columns=LABELS)


def vendor_labels(vendors):
    """Disambiguate normalized duplicate names while keeping UEI as the identity."""
    normalized = vendors.vendor_name.astype(str).str.upper().str.split().str.join(' ')
    duplicate = normalized.duplicated(keep=False)
    # A short suffix usually suffices; use the full UEI if two suffixes collide.
    suffixes = vendors.vendor_id.astype(str).str[-6:]
    pairs = normalized + ' · ' + suffixes
    collisions = pairs.duplicated(keep=False)
    return {row.vendor_id: str(row.vendor_name) +
            (f' · {row.vendor_id if collisions.loc[i] else suffixes.loc[i]}' if duplicate.loc[i] else '')
            for i, row in vendors.iterrows()}
