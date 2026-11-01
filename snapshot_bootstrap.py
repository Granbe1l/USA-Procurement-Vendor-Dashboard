"""Initialize a missing deployment snapshot from the official public source.

This module never creates substitute data. Streamlit caches the caller so one
server initialization serves subsequent sessions and filter changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from threading import Lock

from procurement import load_data
from scripts.fetch_data import FetchError, fetch_dataset
from scripts.prepare_data import prepare

_LOCK = Lock()
_REQUIRED = ('metadata.json', 'quality.json')


def _valid_snapshot(directory: Path) -> bool:
    if not all((directory / name).is_file() for name in _REQUIRED):
        return False
    try:
        metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
        quality = json.loads((directory / 'quality.json').read_text(encoding='utf-8'))
        if not isinstance(metadata, dict) or not isinstance(quality, dict):
            return False
        if metadata.get('status', 'complete') != 'complete':
            return False
        artifacts = [(directory / name, key) for name, key in
                     [('transactions.csv.gz', 'processed_sha256'), ('transactions.parquet', 'parquet_sha256')]
                     if (directory / name).is_file()]
        if not artifacts:
            return False
        for path, checksum_key in artifacts:
            data = load_data(path)
            if data.empty or int(quality.get('retained_rows', -1)) != len(data):
                return False
            if metadata.get(checksum_key):
                with path.open('rb') as handle:
                    digest = hashlib.file_digest(handle, 'sha256').hexdigest()
                if digest != metadata[checksum_key]:
                    return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _promote(staged: Path, target: Path) -> None:
    """Swap only a validated complete bundle; retain any older incomplete files."""
    backup = None
    if target.exists():
        backup = Path(tempfile.mkdtemp(prefix=f'{target.name}-previous-', dir=target.parent))
        backup.rmdir()
        target.replace(backup)
    try:
        staged.replace(target)
    except OSError:
        if backup is not None:
            backup.replace(target)
        raise


def ensure_snapshot(data_dir: Path) -> dict:
    """Reuse a valid local snapshot, or obtain and prepare the complete cohort.

    Failure is returned for the UI to cache and expose with an explicit retry.
    Full raw captures (including failed-capture metadata) stay under data/raw;
    incomplete processed outputs never replace the current snapshot.
    """
    data_dir = Path(data_dir)
    with _LOCK:
        if _valid_snapshot(data_dir):
            return {'status': 'ready', 'fetched': False}
        try:
            data_dir.parent.mkdir(parents=True, exist_ok=True)
            metadata_path = Path(fetch_dataset(data_dir.parent / 'raw', timeout=600))
            source_metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            if (source_metadata.get('status') != 'complete'
                    or source_metadata.get('source_verification') != 'official_api_download_count_checked'):
                raise ValueError('Official download did not pass source and count verification.')
            checksum = source_metadata.get('raw_sha256')
            count_fields = ('raw_row_count', 'transaction_count_before', 'transaction_count_after')
            if (not isinstance(checksum, str) or len(checksum) != 64
                    or any(char not in '0123456789abcdef' for char in checksum)
                    or any(type(source_metadata.get(name)) is not int or source_metadata[name] < 1
                           for name in count_fields)):
                raise ValueError('Official download is missing required SHA-256 or source-count evidence.')
            raw_name = source_metadata.get('raw_file')
            if not isinstance(raw_name, str) or not raw_name or Path(raw_name).name != raw_name or '\\' in raw_name:
                raise ValueError('Official download metadata does not identify a safe source CSV.')
            raw_path = metadata_path.parent / raw_name
            if raw_path.resolve().parent != metadata_path.parent.resolve():
                raise ValueError('Source CSV must be inside the downloaded capture directory.')
            with tempfile.TemporaryDirectory(prefix='.procurement-prepare-', dir=data_dir.parent) as temp:
                staged = Path(temp) / 'processed'
                prepare(raw_path, metadata_path, staged)
                if not (staged / 'summary.json').is_file() or not _valid_snapshot(staged):
                    raise ValueError('The official snapshot did not produce a complete nonempty analysis bundle.')
                metadata = json.loads((staged / 'metadata.json').read_text(encoding='utf-8'))
                metadata['processed_sha256'] = hashlib.sha256((staged / 'transactions.csv.gz').read_bytes()).hexdigest()
                (staged / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
                _promote(staged, data_dir)
            return {'status': 'ready', 'fetched': True}
        except (FetchError, ValueError, KeyError, TypeError) as exc:
            return {'status': 'error', 'fetched': False, 'error': str(exc)}
        except OSError:
            return {'status': 'error', 'fetched': False,
                    'error': 'The snapshot could not be saved to application storage. Retry the official download.'}
