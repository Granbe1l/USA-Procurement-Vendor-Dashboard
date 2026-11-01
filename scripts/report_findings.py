"""Print query-backed README findings only from a verified official local bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procurement import load_data
from src.db import run_sql_file
from src.insights import build_findings


def report(directory):
    directory = Path(directory)
    metadata = json.loads((directory / 'metadata.json').read_text())
    quality = json.loads((directory / 'quality.json').read_text())
    if metadata.get('fixture_notice') or 'synthetic' in str(metadata.get('source', '')).lower():
        raise ValueError('Synthetic fixtures cannot produce portfolio findings.')
    if metadata.get('status') != 'complete' or metadata.get('source_verification') != 'official_api_download_count_checked':
        raise ValueError('A count-checked official capture is required; fixtures/unverified imports cannot produce portfolio findings.')
    raw_hash = metadata.get('raw_sha256', '')
    if len(raw_hash) != 64 or any(c not in '0123456789abcdef' for c in raw_hash):
        raise ValueError('Missing raw-capture checksum evidence.')
    for key in ['raw_row_count', 'transaction_count_before', 'transaction_count_after']:
        if type(metadata.get(key)) is not int or metadata[key] <= 0:
            raise ValueError('Missing positive source-count evidence.')
    if len({metadata[key] for key in ['raw_row_count', 'transaction_count_before', 'transaction_count_after']}) != 1:
        raise ValueError('Source counts do not reconcile.')
    name, key = ('transactions.parquet', 'parquet_sha256') if (directory / 'transactions.parquet').exists() else ('transactions.csv.gz', 'processed_sha256')
    path = directory / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get(key):
        raise ValueError('The processed checksum does not match the capture.')
    frame = load_data(path)
    if frame.empty or len(frame) != quality.get('retained_rows') or quality.get('initial_rows') != metadata['raw_row_count']:
        raise ValueError('The processed row count does not match the cleaning audit.')
    concentration = run_sql_file('04_concentration_hhi.sql', data_path=path)
    annual = run_sql_file('06_fy_comparison.sql', data_path=path)
    lines = ['## Key Findings', '', 'Snapshot retrieved: ' + str(metadata.get('retrieval_finished_at', 'not recorded')), '']
    for headline, _, source in build_findings(concentration, annual):
        lines.append(f'- {headline} (`sql/{source}`)')
    # Query the combined ABC population across the full observed FY scope.
    summary = run_sql_file('03_abc_summary.sql', data_path=path)
    a = summary.loc[summary.scope.eq('combined') & summary.category.eq('A')]
    if len(a) and a.iloc[0].vendor_count:
        row = a.iloc[0]
        years = ', '.join(f'FY{year}' for year in sorted(frame.fiscal_year.unique()))
        lines.append(f'- NSF and NRC combined, {years}: {int(row.vendor_count):,} Category A recipients '
                     f'({row.vendor_share:.1%} of identified recipients), with {row.value_share:.1%} of positive-net vendor value. '
                     '(`sql/03_abc_summary.sql`)')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data' / 'processed')
    args = parser.parse_args()
    try:
        print(report(args.data_dir))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Findings not generated: {exc}\n')


if __name__ == '__main__':
    main()
