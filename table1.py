"""
table1.py - summary statistics of BET-TR and the 13 fixed stocks (paper Table 1).

Returns cover every calendar month from each stock's first month to December 2025
(a month without trades has 0% return), so the annual return is a true calendar-time
growth rate. The liquidity filter only decides which stocks can be SELECTED; the
number of months it excludes is shown in its own column.

Saves table1.xlsx.
"""
import numpy as np
import pandas as pd

from common import CORE, EXTRA, load_all

index_m, stocks = load_all()
assets = {'BET-TR': index_m, **{t: stocks[t] for t in CORE + EXTRA if t in stocks}}

rows = []
for name, m in assets.items():
    r = m['ret_1m'].dropna()
    calendar = pd.period_range(r.index.min(), r.index.max(), freq='M')
    assert len(calendar) == len(r), f'{name}: returns are not on a continuous calendar'

    years = len(r) / 12
    excluded = int((~m['liquid']).reindex(r.index).fillna(False).sum()) if 'liquid' in m else 0
    rows.append({'Ticker': name,
                 'First month': str(r.index.min()),
                 'Months': len(r),
                 'Months excluded by liquidity filter': excluded,
                 'Mean monthly return': r.mean(),
                 'Annualised volatility': r.std() * np.sqrt(12),
                 'Annualised return (CAGR)': (1 + r).prod() ** (1 / years) - 1})

table = pd.DataFrame(rows)
print(table.to_string(index=False, formatters={
    'Mean monthly return': '{:.2%}'.format,
    'Annualised volatility': '{:.1%}'.format,
    'Annualised return (CAGR)': '{:.1%}'.format}))
table.to_excel('table1.xlsx', index=False)
print('\nSaved table1.xlsx')
