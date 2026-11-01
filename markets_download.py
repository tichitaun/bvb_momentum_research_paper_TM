"""
Step 1 of the cross-market comparison: download all stocks of the four markets.
Saves data/<Market>/<TICKER>.csv and prints a data-quality summary per stock.
Run from the folder that contains markets_config.py.
"""
import os
import yfinance as yf
from markets_config import MARKETS, START, END, FLAG_THRESHOLD

os.chdir(os.path.dirname(os.path.abspath(__file__)))

for market, cfg in MARKETS.items():
    folder = os.path.join('data', market)
    os.makedirs(folder, exist_ok=True)
    print(f'\n===== {market} =====')
    print(f"{'ticker':10s}{'first day':12s}{'last day':12s}{'rows':>6s}{'zero-vol':>10s}{'flags':>7s}")
    for t in cfg['tickers']:
        try:
            df = yf.download(t + cfg['suffix'], start=START, end=END, auto_adjust=False, progress=False)
        except Exception as e:
            print(f'{t:10s}ERROR {e}')
            continue
        if df is None or df.empty:
            print(f'{t:10s}NO DATA - check the ticker on finance.yahoo.com')
            continue
        df.columns = df.columns.get_level_values(0)
        df.to_csv(os.path.join(folder, f'{t}.csv'))
        raw, adj = df['Close'].pct_change(), df['Adj Close'].pct_change()
        flags = ((adj - raw).abs() > FLAG_THRESHOLD).sum()
        print(f'{t:10s}{str(df.index[0].date()):12s}{str(df.index[-1].date()):12s}{len(df):>6d}'
              f'{(df["Volume"] == 0).sum():>10d}{flags:>7d}')
print('\nDone. Send me this output.')
