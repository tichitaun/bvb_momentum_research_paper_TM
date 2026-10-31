"""
download_pool.py - download the 32 BVB stocks from Yahoo Finance (run once).

For each stock: daily prices from January 2015 to December 2025, with BOTH the
unadjusted close ('Close', adjusted for splits only) and the adjusted close
('Adj Close', adjusted for splits and dividends). Saved as <TICKER>_historical_data.csv.

The BET-TR index is NOT on Yahoo: download it by hand from Investing.com and save it as
Bucharest_Total_Return_Historical_Data.xlsx (columns Date and Price).
"""
import yfinance as yf

from common import ALL_STOCKS

START = '2015-01-01'
END = '2026-01-01'      # yfinance does not include the end date -> data up to 31 Dec 2025

print(f"{'ticker':7s}{'first day':12s}{'last day':12s}{'rows':>6s}{'zero-vol':>10s}{'flags':>7s}")
for ticker in ALL_STOCKS:
    try:
        df = yf.download(f'{ticker}.RO', start=START, end=END, auto_adjust=False, progress=False)
    except Exception as error:
        print(f'{ticker:7s}ERROR: {error}')
        continue
    if df.empty:
        print(f'{ticker:7s}NO DATA')
        continue

    df.columns = df.columns.get_level_values(0)        # Yahoo returns a two-row header
    df.to_csv(f'{ticker}_historical_data.csv')

    # quick check: days without trades, and days where the dividend adjustment looks odd
    raw_return = df['Close'].pct_change()
    adj_return = df['Adj Close'].pct_change()
    zero_volume = (df['Volume'] == 0).sum()
    flags = ((adj_return - raw_return).abs() > 0.15).sum()
    print(f'{ticker:7s}{str(df.index[0].date()):12s}{str(df.index[-1].date()):12s}'
          f'{len(df):>6d}{zero_volume:>10d}{flags:>7d}')
