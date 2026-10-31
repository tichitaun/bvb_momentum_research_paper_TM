"""
data_audit.py - check Yahoo's dividend adjustments for every stock.

For every trading day:
    implied payout   = (1 + adjusted return) / (1 + unadjusted return) - 1
    implied dividend = (1 + adjusted return) x previous close - close        (in lei)
On a normal day the payout is 0; on an ex-dividend day it is about dividend / price.

Four lists, saved to data_audit.xlsx:
  A) dividend events Yahoo recognised (payout > 0.5%) -> compare with the BVB calendar
  B) flagged days: adjusted and unadjusted returns differ by > 15 points -> verify by hand
  C) unadjusted drops below -10% with no dividend     -> possible missed dividend
  D) one-day spikes that reverse the next day         -> recording errors (merged)
"""
import pandas as pd

from common import ALL_STOCKS, CORRECTIONS, FLAG_THRESHOLD, find_spikes

events, flagged, drops, spikes = [], [], [], []
stocks_found = 0

for ticker in ALL_STOCKS:
    try:
        df = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'], index_col='Date')
    except FileNotFoundError:
        continue
    stocks_found += 1

    df = df[df['Volume'] > 0]
    close = df['Close']
    raw_return = close.pct_change()
    adj_return = df['Adj Close'].pct_change()
    implied_payout = (1 + adj_return) / (1 + raw_return) - 1
    implied_dividend = (1 + adj_return) * close.shift(1) - close

    for i in find_spikes(adj_return):
        spikes.append(dict(ticker=ticker, date=df.index[i].date(), next_day=df.index[i + 1].date(),
                           return_day=adj_return.iloc[i], return_next_day=adj_return.iloc[i + 1],
                           combined=(1 + adj_return.iloc[i]) * (1 + adj_return.iloc[i + 1]) - 1,
                           same_month=df.index[i].to_period('M') == df.index[i + 1].to_period('M')))

    for day in df.index[1:]:
        row = dict(ticker=ticker, date=day.date(), prev_close=round(close.shift(1)[day], 4),
                   close=round(close[day], 4), raw_return=raw_return[day], adj_return=adj_return[day],
                   implied_payout=implied_payout[day], implied_dividend_lei=implied_dividend[day])
        if implied_payout[day] > 0.005:
            events.append(row)
        if abs(adj_return[day] - raw_return[day]) > FLAG_THRESHOLD:
            row = dict(row, verified_correction=CORRECTIONS.get((ticker, str(day.date())), 'NONE - check!'))
            flagged.append(row)
        if raw_return[day] < -0.10 and abs(implied_payout[day]) < 0.005:
            drops.append(row)

if stocks_found == 0:
    raise SystemExit('No stock CSV files found in this folder - run from the folder with the data.')
print(f'Audited {stocks_found} stocks')

A, B, C, D = (pd.DataFrame(x) for x in (events, flagged, drops, spikes))
pd.set_option('display.width', 220)
pd.set_option('display.max_rows', 400)
percent = '{:.1%}'.format
formats = {'raw_return': percent, 'adj_return': percent, 'implied_payout': percent,
           'implied_dividend_lei': '{:.3f}'.format}

print(f'A) Dividend events recognised by Yahoo: {len(A)} (largest 25 shown, full list in Excel)')
if len(A):
    print(A.sort_values('implied_payout', ascending=False).head(25).to_string(index=False, formatters=formats))
print(f'\nB) Flagged days (adjusted vs unadjusted differ by > {FLAG_THRESHOLD:.0%}): {len(B)}')
if len(B):
    print(B.to_string(index=False, formatters=formats))
print(f'\nC) Unadjusted drops below -10% with no dividend recognised: {len(C)}')
if len(C):
    print(C.to_string(index=False, formatters=formats))
print(f'\nD) One-day spikes reversed the next day (merged into one two-day return): {len(D)}')
if len(D):
    print(D.to_string(index=False, formatters={'return_day': percent, 'return_next_day': percent,
                                               'combined': percent}))

with pd.ExcelWriter('data_audit.xlsx') as xw:
    A.to_excel(xw, sheet_name='A_dividend_events', index=False)
    B.to_excel(xw, sheet_name='B_flagged_days', index=False)
    C.to_excel(xw, sheet_name='C_large_drops', index=False)
    D.to_excel(xw, sheet_name='D_one_day_spikes', index=False)
print('\nSaved data_audit.xlsx')
