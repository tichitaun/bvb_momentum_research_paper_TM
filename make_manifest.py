"""
make_manifest.py - record exactly which data and software produced the results.

Writes:
  data_manifest.csv - every input file: size, SHA-256 hash (a fingerprint of the file),
                      last-modified time, rows, first and last date, duplicate dates
  environment.txt   - Python and package versions
If a replicator's files have the same hashes, they are using exactly the same data.
"""
import glob
import hashlib
import os
import platform
import sys
from datetime import datetime

import pandas as pd

# output files of our own scripts are not inputs, so they are skipped
OUTPUT_PREFIXES = ('results', 'robustness', 'long_only', 'concentration', 'universe', 'walk_forward',
                   'costs', 'losers', 'inference', 'table1', 'data_audit', 'values_1000')


def sha256_of(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


rows = []
input_files = sorted(glob.glob('*_historical_data.csv')) + sorted(glob.glob('*.xlsx'))
for path in input_files:
    if path.startswith(OUTPUT_PREFIXES):
        continue
    row = dict(file=path, bytes=os.path.getsize(path), sha256=sha256_of(path),
               modified=datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec='seconds'))
    try:
        data = pd.read_csv(path) if path.endswith('.csv') else pd.read_excel(path)
        dates = pd.to_datetime(data['Date'])
        row.update(rows=len(data), first_date=dates.min().date(), last_date=dates.max().date(),
                   duplicate_dates=int(dates.duplicated().sum()))
    except Exception as error:
        row.update(note=f'could not read dates: {error}')
    rows.append(row)

pd.DataFrame(rows).to_csv('data_manifest.csv', index=False)


def version_of(module_name):
    try:
        module = __import__(module_name)
        return getattr(module, '__version__', 'unknown')
    except ImportError:
        return 'not installed'


with open('environment.txt', 'w') as f:
    f.write(f'run date: {datetime.now().isoformat(timespec="seconds")}\n')
    f.write(f'python: {sys.version.split()[0]} ({platform.platform()})\n')
    for name in ['pandas', 'numpy', 'scipy', 'statsmodels', 'matplotlib', 'openpyxl', 'yfinance']:
        f.write(f'{name}: {version_of(name)}\n')

duplicates = sum(r.get('duplicate_dates', 0) for r in rows)
print(f'{len(rows)} input files recorded in data_manifest.csv ({duplicates} duplicate dates); '
      f'versions in environment.txt')
