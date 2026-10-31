"""
common.py - everything the analysis scripts share.

    1. Settings        : tickers, sectors, signals, rules (30%, 80%, ...)
    2. Risk-free rate  : the BNR policy rate, converted to a monthly rate
    3. Daily data      : read a stock, fix dividend errors, rebuild a total-return price
    4. Monthly data    : month-end prices, past returns (signals) and next-month return
    5. Universes       : the fixed 13 stocks and the rule-based "15 most liquid" universe
    6. Statistics      : significance stars, mean test, performance and alpha
    7. Charts          : saving figures and drawing "growth of 1 leu" lines

TIMING CONVENTION (used everywhere)
-----------------------------------
Each monthly row is a FORMATION month t:
    trail_Jm    = return from the end of month t-J to the end of month t   -> known at t
    trail_12_1m = return from the end of month t-12 to the end of month t-1 -> known at t
    next_1m     = return from the end of month t to the end of month t+1   -> earned AFTER t
A portfolio is chosen at the end of month t (with trail_* only) and earns next_1m.
"""
import time

import numpy as np
import pandas as pd
import statsmodels.api as sm


# =============================================================================
# 1. SETTINGS
# =============================================================================

# The seven large core stocks and the six stocks added to make the fixed 13
CORE = ['TLV', 'BRD', 'SNG', 'SNN', 'SNP', 'TEL', 'TGN']
EXTRA = ['ALR', 'ATB', 'ARS', 'DIGI', 'M', 'SFG']
UNIVERSES = {'core': CORE, 'extended': CORE + EXTRA}

# The other 19 stocks of the 32-stock pool used by the rule-based universe
POOL_EXTRA = ['EL', 'COTE', 'OIL', 'RRC', 'BVB', 'TRP', 'VNC', 'ROCE', 'ELMA', 'TBM', 'SNO',
              'IMP', 'ONE', 'WINE', 'AQ', 'TTS', 'H2O', 'BIO', 'BNET']
ALL_STOCKS = CORE + EXTRA + POOL_EXTRA

# Sector of every stock (used by the sector-neutral tests)
SECTORS = {
    'TLV': 'Banks', 'BRD': 'Banks', 'BVB': 'Banks',          # BVB (the exchange) grouped with banks
    'SNP': 'Oil & gas', 'SNG': 'Oil & gas', 'COTE': 'Oil & gas', 'OIL': 'Oil & gas', 'RRC': 'Oil & gas',
    'SNN': 'Power & utilities', 'TEL': 'Power & utilities', 'TGN': 'Power & utilities',
    'EL': 'Power & utilities', 'H2O': 'Power & utilities',
    'ALR': 'Industrials', 'ARS': 'Industrials', 'TRP': 'Industrials', 'VNC': 'Industrials',
    'ROCE': 'Industrials', 'ELMA': 'Industrials', 'TBM': 'Industrials', 'SNO': 'Industrials',
    'TTS': 'Industrials',
    'ATB': 'Healthcare', 'M': 'Healthcare', 'BIO': 'Healthcare',
    'DIGI': 'Consumer & telecom', 'SFG': 'Consumer & telecom', 'WINE': 'Consumer & telecom',
    'AQ': 'Consumer & telecom', 'BNET': 'Consumer & telecom',
    'IMP': 'Real estate', 'ONE': 'Real estate',
}

INDEX_FILE = 'Bucharest_Total_Return_Historical_Data.xlsx'   # BET-TR, from Investing.com

HORIZONS = [1, 3, 6, 12]                                       # look-back lengths in months
SIGNALS = ['trail_1m', 'trail_3m', 'trail_6m', 'trail_12m', 'trail_12_1m']
MAIN = 'trail_12_1m'                                           # the pre-specified main signal

FRACTION = 0.30      # winners = top 30% of stocks, losers = bottom 30% (at least 2 each)
MIN_TRADED = 0.80    # a stock must trade on >= 80% of the exchange's trading days in a month
K_MAIN = 15          # size of the rule-based universe
BASE_COST = 0.005    # baseline trading cost: 0.5% per leu bought or sold (one-way)


# =============================================================================
# 2. RISK-FREE RATE
# =============================================================================

# BNR monetary policy rate (% per year). Each rate applies from the month it took effect.
# 2015 checked against BNR announcements: 2.50% from 8 Jan, 2.25% in Feb, 2.00% from 1 Apr,
# 1.75% from 7 May.
BNR_CHANGES = {
    '2015-01': 2.50, '2015-02': 2.25, '2015-04': 2.00, '2015-05': 1.75,
    '2018-01': 2.00, '2018-02': 2.25, '2018-05': 2.50,
    '2020-03': 2.00, '2020-05': 1.75, '2020-08': 1.50, '2021-01': 1.25,
    '2021-10': 1.50, '2021-11': 1.75, '2022-01': 2.00, '2022-02': 2.50,
    '2022-04': 3.00, '2022-05': 3.75, '2022-07': 4.75, '2022-08': 5.50,
    '2022-10': 6.25, '2022-11': 6.75, '2023-01': 7.00,
    '2024-07': 6.75, '2024-08': 6.50,
}
RF_CONVENTION = 'simple'   # 'simple': annual / 12      'effective': (1 + annual)^(1/12) - 1


def monthly_rf(months):
    """Monthly risk-free return for each month in `months` (a PeriodIndex).

    Example: in a month when the BNR rate is 6.5%, the simple convention gives 0.065 / 12.
    """
    # one row per change -> one row per calendar month, each month keeps the latest rate
    changes = pd.Series({pd.Period(month, 'M'): rate for month, rate in BNR_CHANGES.items()})
    every_month = pd.period_range(changes.index.min(), max(months), freq='M')
    annual_rate = changes.reindex(every_month).ffill() / 100

    if RF_CONVENTION == 'simple':
        monthly = annual_rate / 12
    else:
        monthly = (1 + annual_rate) ** (1 / 12) - 1
    return monthly.reindex(months).values


def rf_for_holding_month(formation_months):
    """Risk-free return earned DURING the holding month (t+1) of each formation month t."""
    return pd.Series(monthly_rf(formation_months + 1), index=formation_months)


# =============================================================================
# 3. DAILY DATA: reading a stock and fixing dividend errors
# =============================================================================

# Yahoo's dividend adjustment was checked against company filings. When it was wrong, the
# day's total return is rebuilt from UNADJUSTED prices:  (P_t + D) / P_t-1 - 1
#   (ticker, date of the price drop in the data) -> gross dividend D in lei, or 'raw'
#   'raw' = the corporate action cannot be rebuilt reliably, use the unadjusted price change
CORRECTIONS = {
    # Nuclearelectrica special dividend 1.61 lei, ex-date 21 Dec 2018 (Central Depository).
    # Yahoo implied 4.09 lei.
    ('SNN', '2018-12-21'): 1.61,
    # Alro dividend 0.45756 lei, official ex-date 7 Jan 2019 (Alro investor relations).
    ('ALR', '2019-01-08'): 0.45756,
    # Romcarbon dividend 0.010 lei, ex-date 8 Dec 2022 (BVB report). Halved to 0.005 because
    # Yahoo prices are adjusted for Romcarbon's 1:1 bonus issue of 2023.
    ('ROCE', '2022-12-08'): 0.005,
    # Bittnet bonus issue (6 new per 10) plus an optional distribution, ex-date 20 Jul 2021.
    ('BNET', '2021-07-20'): 'raw',
}
FLAG_THRESHOLD = 0.15   # adjusted vs unadjusted return differ by >15 points -> check by hand
SPIKE_SIZE = 0.30       # a one-day jump of more than 30% ...
SPIKE_REVERSAL = 0.10   # ... that is undone the next day (two-day return within +-10%)


def find_spikes(daily_returns):
    """Positions i where the price jumps >30% on day i and comes back on day i+1.

    Such a jump-and-return is a recording error, not a real price move.
    """
    r = daily_returns.values
    spikes = []
    for i in range(1, len(r) - 1):
        jump_is_big = abs(r[i]) > SPIKE_SIZE
        two_day_return = (1 + r[i]) * (1 + r[i + 1]) - 1
        if jump_is_big and abs(two_day_return) < SPIKE_REVERSAL:
            spikes.append(i)
    return spikes


def load_stock(ticker):
    """Read one Yahoo CSV and return a daily total-return price (columns Date, Price).

    Steps:
      1. keep only days with trades (zero-volume days are mostly holidays)
      2. daily total return = change in the dividend-adjusted price
      3. replace the return on days listed in CORRECTIONS
      4. merge one-day spikes into a single two-day return
      5. warn about any other suspicious day
      6. rebuild the price by compounding the daily returns (starts at 1)
    Changing one day's RETURN leaves every other day's return unchanged, so the rebuilt
    price series stays consistent.
    """
    df = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'], index_col='Date')

    # 1. only days with trades
    df = df[df['Volume'] > 0]
    raw_close = df['Close']                               # adjusted for splits only
    raw_return = raw_close.pct_change()                   # price change without dividends
    total_return = df['Adj Close'].pct_change()           # price change including dividends

    # 3. verified corrections
    handled_days = []
    for (corr_ticker, day), fix in CORRECTIONS.items():
        if corr_ticker != ticker:
            continue
        day = pd.Timestamp(day)
        if day not in df.index:
            print(f'WARNING {ticker} {day.date()}: correction date has no trades in the data '
                  f'- correction NOT applied')
            continue
        i = df.index.get_loc(day)
        if fix == 'raw':
            total_return.iloc[i] = raw_return.iloc[i]
        else:
            dividend = fix
            total_return.iloc[i] = (raw_close.iloc[i] + dividend) / raw_close.iloc[i - 1] - 1
        handled_days.append(day)

    # 4. one-day spikes: put the whole two-day move on the second day
    for i in find_spikes(total_return):
        two_day = (1 + total_return.iloc[i]) * (1 + total_return.iloc[i + 1]) - 1
        total_return.iloc[i] = 0.0
        total_return.iloc[i + 1] = two_day
        handled_days += [df.index[i], df.index[i + 1]]

    # 5. any other day where adjusted and unadjusted returns differ a lot
    gap = (total_return - raw_return).abs()
    for day in df.index[gap > FLAG_THRESHOLD]:
        if day not in handled_days:
            print(f'WARNING {ticker} {day.date()}: adjusted and unadjusted returns differ by more '
                  f'than {FLAG_THRESHOLD:.0%} and no verified correction exists - check data_audit.xlsx')

    # 6. rebuild the total-return price (first day has no return -> 0)
    price = (1 + total_return.fillna(0)).cumprod()
    return price.rename('Price').reset_index()


def load_index(path=INDEX_FILE):
    """Read the BET-TR file (columns Date, Price)."""
    df = pd.read_excel(path)[['Date', 'Price']]
    df['Date'] = pd.to_datetime(df['Date'])
    if not pd.api.types.is_numeric_dtype(df['Price']):
        # prices saved as text, e.g. '36,872.05' -> 36872.05
        df['Price'] = df['Price'].astype(str).str.replace(',', '').astype(float)
    return df


def trading_days_per_month(index_daily):
    """Number of days the exchange was open in each month (days with a BET-TR value)."""
    return index_daily.groupby(index_daily['Date'].dt.to_period('M')).size()


# =============================================================================
# 4. MONTHLY DATA
# =============================================================================

def to_monthly(daily):
    """Daily prices -> one row per calendar month with all return variables.

    - the month-end price is the last traded price of the month
    - a month with no trades keeps the previous price (a holder could not trade, so the
      price is unchanged); this keeps exactly one row per calendar month
    - an incomplete last month (data ending before the 25th) is dropped
    """
    df = daily.sort_values('Date').copy()
    df['YearMonth'] = df['Date'].dt.to_period('M')

    month_end = df.groupby('YearMonth').tail(1).set_index('YearMonth')
    days_traded = df.groupby('YearMonth').size()

    if month_end['Date'].iloc[-1].day < 25:
        month_end = month_end.iloc[:-1]

    calendar = pd.period_range(month_end.index.min(), month_end.index.max(), freq='M')
    m = month_end.reindex(calendar)
    m.index.name = 'YearMonth'
    m['Price'] = m['Price'].ffill()
    m['days_traded'] = days_traded.reindex(calendar).fillna(0)

    P = m['Price']
    m['ret_1m'] = P / P.shift(1) - 1                       # return during month t
    for J in HORIZONS:
        m[f'trail_{J}m'] = P / P.shift(J) - 1              # past J months, known at t
    m['trail_12_1m'] = P.shift(1) / P.shift(12) - 1        # months t-12 .. t-1, known at t
    m['next_1m'] = m['ret_1m'].shift(-1)                   # return during month t+1
    return m


def apply_liquidity_filter(m, index_days):
    """Mark months in which the stock traded on fewer than 80% of trading days.

    In those months its signals are blanked, so it cannot be selected by any strategy.
    (If the exchange's trading days are unknown for a month, the stock is kept.)
    """
    share_of_days = m['days_traded'] / index_days.reindex(m.index)
    m['liquid'] = (share_of_days >= MIN_TRADED) | share_of_days.isna()
    m.loc[~m['liquid'], SIGNALS] = np.nan
    return m


# =============================================================================
# 5. UNIVERSES
# =============================================================================

def load_all():
    """BET-TR (monthly) and the 13 stocks of the fixed universe (monthly, filtered)."""
    index_daily = load_index()
    index_days = trading_days_per_month(index_daily)
    index_m = to_monthly(index_daily)

    stocks = {}
    for ticker in CORE + EXTRA:
        try:
            stocks[ticker] = apply_liquidity_filter(to_monthly(load_stock(ticker)), index_days)
        except FileNotFoundError:
            print(f'{ticker}: file not found, skipped')
    return index_m, stocks


def load_pool():
    """BET-TR and all 32 stocks of the pool, each with its 12-month average daily traded value.

    adv_12m at month t = average over months t-11..t of (lei traded in the month / trading
    days in the month). Months without trades count as zero. Only past data is used.
    """
    index_daily = load_index()
    index_days = trading_days_per_month(index_daily)
    index_m = to_monthly(index_daily)

    stocks = {}
    for ticker in ALL_STOCKS:
        try:
            m = apply_liquidity_filter(to_monthly(load_stock(ticker)), index_days)
            daily = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'])
        except FileNotFoundError:
            print(f'{ticker}: no file, skipped')
            continue

        daily['value'] = daily['Close'] * daily['Volume']            # lei traded that day
        value_per_month = daily.groupby(daily['Date'].dt.to_period('M'))['value'].sum()
        calendar = pd.period_range(value_per_month.index.min(), value_per_month.index.max(), freq='M')
        value_per_month = value_per_month.reindex(calendar, fill_value=0)

        avg_daily_value = value_per_month / index_days.reindex(calendar)
        m['adv_12m'] = avg_daily_value.rolling(12, min_periods=12).mean().reindex(m.index)
        stocks[ticker] = m
    return index_m, stocks


def membership(stocks, k=K_MAIN):
    """Table (months x stocks) of True/False: is the stock in the k-stock universe at t?

    Eligible at t: passed the liquidity filter in t, has a 12-month traded value, and has a
    12-1 signal (12 months of history). The k eligible stocks with the highest 12-month
    average daily traded value form the universe.
    """
    traded_value = pd.DataFrame({t: m['adv_12m'] for t, m in stocks.items()})
    eligible = pd.DataFrame({t: m['liquid'] & m['adv_12m'].notna() & m[MAIN].notna()
                             for t, m in stocks.items()})
    eligible = eligible.reindex(traded_value.index).fillna(False)

    rank = traded_value.where(eligible).rank(axis=1, ascending=False)   # 1 = most traded
    return rank <= k


def restrict(stocks, member):
    """Copy of the stocks where all signals are blank whenever a stock is outside the universe.

    A stock with a blank signal cannot be selected, so every strategy automatically only
    chooses from the universe of that month.
    """
    restricted = {}
    for ticker, m in stocks.items():
        m = m.copy()
        inside = member[ticker].reindex(m.index).fillna(False).astype(bool)
        m.loc[~inside, SIGNALS] = np.nan
        if inside.any():
            restricted[ticker] = m
    return restricted


def fixed_universe(pool):
    """The fixed 13 stocks taken from the pool."""
    return {t: pool[t] for t in CORE + EXTRA if t in pool}


def rule_based_universe(pool, k=K_MAIN):
    """The rule-based universe: each month the k most liquid stocks."""
    return restrict(pool, membership(pool, k))


# =============================================================================
# 6. STATISTICS
# =============================================================================

def stars(p):
    """Significance stars: *** p<0.01, ** p<0.05, * p<0.10."""
    if p < 0.01:
        return '***'
    if p < 0.05:
        return '**'
    if p < 0.10:
        return '*'
    return ''


def mean_test(x, lags=3):
    """Is the average of a monthly series different from zero?

    Regression of x on a constant; the constant is the mean, and its t-statistic uses
    Newey-West standard errors (robust to autocorrelation up to `lags` months).
    Returns (mean, t, p).
    """
    x = pd.Series(x).dropna()
    fit = sm.OLS(x.values, np.ones(len(x))).fit(cov_type='HAC', cov_kwds={'maxlags': lags})
    return x.mean(), fit.tvalues[0], fit.pvalues[0]


def summarize(series, label):
    """One table row for a monthly return series (e.g. winners minus losers)."""
    mean, t, p = mean_test(series)
    return dict(test=label, mean_monthly=mean, annualized=mean * 12, t_NW=t, p=p,
                sig=stars(p), months=len(series), pct_positive=(series > 0).mean())


def annual_return(monthly_returns):
    """Compound annual growth rate (CAGR) of consecutive monthly returns."""
    wealth = (1 + monthly_returns).cumprod()
    return wealth.iloc[-1] ** (12 / len(monthly_returns)) - 1


def max_drawdown(monthly_returns):
    """Worst fall from a previous peak of the wealth path."""
    wealth = (1 + monthly_returns).cumprod()
    return (wealth / wealth.cummax() - 1).min()


def sharpe_ratio(monthly_returns, rf):
    """Annualised Sharpe ratio: mean excess return / std of excess return * sqrt(12)."""
    excess = monthly_returns - rf
    return excess.mean() / excess.std() * np.sqrt(12)


def evaluate(r, bench, rf, label, turnover=None):
    """Full performance row for a strategy's monthly returns r (indexed by formation month).

    Includes the alpha and beta from:  (r - rf) = alpha + beta * (bench - rf) + error
    with Newey-West standard errors (3 lags). Alpha is multiplied by 12 (annual).
    r must cover consecutive months, so that the annual return is a calendar-time CAGR.
    """
    calendar = pd.period_range(r.index.min(), r.index.max(), freq='M')
    assert len(calendar) == len(r) and r.notna().all(), f'{label}: returns must be consecutive months'

    excess, bench_excess = r - rf, bench - rf
    fit = sm.OLS(excess, sm.add_constant(bench_excess)).fit(cov_type='HAC', cov_kwds={'maxlags': 3})
    alpha_p = fit.pvalues['const']

    return dict(portfolio=label,
                ann_return=annual_return(r),
                ann_vol=r.std() * np.sqrt(12),
                sharpe=excess.mean() / excess.std() * np.sqrt(12),
                max_dd=max_drawdown(r),
                beat_BET_pct=(r > bench).mean(),
                alpha_annual=fit.params['const'] * 12,
                t_alpha=fit.tvalues['const'],
                p_alpha=alpha_p,
                sig=stars(alpha_p),
                beta_vs_BET=fit.params.iloc[1],
                annual_turnover=np.nan if turnover is None else turnover.mean() * 12,
                months=len(r))


def calendar_year_returns(monthly):
    """Compound monthly returns (indexed by FORMATION month) into calendar-year returns.

    The return of formation month t is earned in month t+1, so it belongs to the year of t+1.
    Example: the portfolio formed in December 2019 earns January 2020 -> counted in 2020.
    """
    year_earned = (monthly.index + 1).year
    yearly = (1 + monthly).groupby(year_earned).prod() - 1
    return yearly


def print_table(title, df, decimals=4):
    print(f'\n=== {title} ===')
    print(df.round(decimals).to_string(index=False))


# =============================================================================
# 7. CHARTS
# =============================================================================

def save_fig(fig, filename, dpi=200):
    """Save a chart. If the file is locked (open in a viewer, being synced), save under a
    new name instead of crashing."""
    try:
        fig.savefig(filename, dpi=dpi)
    except OSError as error:
        alt = filename.replace('.png', f'_{time.strftime("%H%M%S")}.png')
        print(f'WARNING: could not write {filename} ({error}). Is it open in another program? '
              f'Saved as {alt} instead.')
        fig.savefig(alt, dpi=dpi)


def wealth_path(monthly_returns, start=1.0):
    """Value of `start` invested, shown at the end of the month in which each return is EARNED.

    The first point is the starting value at the end of the first formation month.
    """
    r = monthly_returns.dropna()
    value = start * (1 + r).cumprod()
    value.index = r.index + 1                             # earned one month after formation
    first_point = pd.Series([start], index=[r.index[0]])
    path = pd.concat([first_point, value])
    path.index = path.index.to_timestamp()
    return path


def log_axis_in_multiples(ax):
    """Log scale with readable labels 1x, 2x, 5x, 10x ... instead of 10^1."""
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    ax.set_yscale('log')
    ax.yaxis.set_major_locator(FixedLocator([0.5, 1, 2, 3, 5, 10, 20, 30, 50, 100]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:g}x'))
    ax.grid(True, axis='y', alpha=0.3)
