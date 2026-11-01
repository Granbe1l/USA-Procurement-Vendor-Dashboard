"""Never turn unit fixtures into government-source portfolio findings."""
import hashlib
import json

import pandas as pd
import pytest

from scripts.prepare_data import prepare
from scripts.report_findings import report


def test_report_requires_evidence_and_checks_format_hash(tmp_path):
    raw = tmp_path / 'raw.csv'
    pd.DataFrame([dict(transaction_id='synthetic', vendor_id='test', vendor_name='Test',
                       award_id='test', action_date='2024-01-01', agency='National Science Foundation',
                       state='NY', award_type='D', obligation='1.00')]).to_csv(raw, index=False)
    target = tmp_path / 'processed'
    prepare(raw, output_dir=target)
    with pytest.raises(ValueError, match='official capture'):
        report(target)
    metadata = json.loads((target / 'metadata.json').read_text())
    # Exercise evidence paths locally only. These records never enter production.
    metadata.update(status='complete', source_verification='official_api_download_count_checked',
                    raw_row_count=1, transaction_count_before=1, transaction_count_after=1,
                    source='Synthetic unit fixture', fixture_notice='SYNTHETIC TEST ONLY')
    (target / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='Synthetic'):
        report(target)
    metadata.pop('fixture_notice')
    metadata['source'] = 'Unit-test transport simulation'
    metadata['parquet_sha256'] = '0' * 64
    (target / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='checksum'):
        report(target)
    metadata['parquet_sha256'] = hashlib.sha256((target / 'transactions.parquet').read_bytes()).hexdigest()
    (target / 'metadata.json').write_text(json.dumps(metadata))
    output = report(target)
    assert '100.0%' in output
    assert '04_concentration_hhi.sql' in output
    assert '03_abc_summary.sql' in output
    metadata['transaction_count_after'] = 2
    (target / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='reconcile'):
        report(target)
