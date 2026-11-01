"""
markets_analysis.py - the same tests in Romania, Greece, Poland and Germany (paper Table 10).

Identical rules in every market:
  universe : each month, the 15 most liquid stocks (12-month average daily traded value),
             among stocks with 12 months of history that traded on >= 80% of the days
  signal   : 12-1 month past return (main), plus 3, 6 and 12 months
  tests    : A) winners minus losers (top 30% - bottom 30%), universes of 15 and 10 stocks
             B) split into (winners - all stocks) and (all stocks - losers)
             C) avoid-losers portfolio (all stocks except the bottom 30%) after stock-specific
                costs (half the estimated spread + commission), against all stocks
             D) in how many calendar years the losers lagged
             E) is each market's loser effect different from Germany's?
This folder is self-contained (it does not use the scripts of the main folder).
Saves markets_results.xlsx, markets_effects.png and markets_avoid_losers.png.
"""
import os
import warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from markets_config import (MARKETS, K_UNIVERSE, K_ROBUST, FRACTION, MIN_TRADED,
                            COMMISSION, FLAG_THRESHOLD)

warnings.filterwarnings('ignore')     # hide library deprecation messages in the console
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SIGNALS = ['trail_3m', 'trail_6m', 'trail_12m', 'trail_12_1m']
MAIN = 'trail_12_1m'
FALLBACK_SPREAD = 0.02
MISSING_LOG = []       # chosen stocks without a next-month return (never happens in our data)


# =============================================================================
# Statistics helpers
# =============================================================================

def stars(p):
    if p < 0.01:
        return '***'
    if p < 0.05:
        return '**'
    if p < 0.10:
        return '*'
    return ''


def mean_test(x):
    """Annualised mean of a monthly series, its Newey-West t (3 lags), p and length."""
    x = pd.Series(x).dropna()
    fit = sm.OLS(x.values, np.ones(len(x))).fit(cov_type='HAC', cov_kwds={'maxlags': 3})
    return x.mean() * 12, fit.tvalues[0], fit.pvalues[0], len(x)


def holm(p_values):
    """Holm (1979) adjustment: sort p-values from smallest to largest, multiply the first by m,
    the second by m-1, ... and never let an adjusted value fall below the previous one."""
    p = np.asarray(p_values, float)
    adjusted = np.empty(len(p))
    running_max = 0.0
    for rank, i in enumerate(np.argsort(p)):
        running_max = max(running_max, min(1.0, (len(p) - rank) * p[i]))
        adjusted[i] = running_max
    return adjusted


def monthly_rf(rates, months):
    """Monthly risk-free return from a {month: annual % rate} table (simple convention)."""
    changes = pd.Series({pd.Period(month, 'M'): rate for month, rate in rates.items()})
    every_month = pd.period_range(changes.index.min(), max(months), freq='M')
    return (changes.reindex(every_month).ffill() / 100 / 12).reindex(months).values


def performance(r, rf):
    r = r.dropna()
    rf = rf.reindex(r.index)
    wealth = (1 + r).cumprod()
    excess = r - rf
    return dict(ann_return=wealth.iloc[-1] ** (12 / len(r)) - 1,
                ann_vol=r.std() * np.sqrt(12),
                sharpe=excess.mean() / excess.std() * np.sqrt(12),
                max_dd=(wealth / wealth.cummax() - 1).min())


def alpha_against(r, benchmark, rf):
    data = pd.DataFrame({'y': r - rf, 'x': benchmark - rf}).dropna()
    fit = sm.OLS(data['y'], sm.add_constant(data['x'])).fit(cov_type='HAC', cov_kwds={'maxlags': 3})
    return fit.params['const'] * 12, fit.tvalues['const'], fit.pvalues['const']


# =============================================================================
# Data
# =============================================================================

def find_spikes(r):
    """Days with a >30% jump that is undone the next day (recording errors)."""
    values = r.values
    return [i for i in range(1, len(values) - 1)
            if abs(values[i]) > 0.30 and abs((1 + values[i]) * (1 + values[i + 1]) - 1) < 0.10]


def load_stock(market, ticker, corrections, flags_log):
    """Daily data of one stock with its corrected total return ('ret') and spread inputs."""
    df = pd.read_csv(os.path.join('data', market, f'{ticker}.csv'), parse_dates=['Date'], index_col='Date')
    df = df[df['Volume'] > 0].copy()
    if len(df) < 30:
        return None

    raw_return = df['Close'].pct_change()
    total_return = df['Adj Close'].pct_change()

    # verified corrections: (P_t + dividend) / P_t-1 - 1, or the unadjusted change ('raw')
    handled_days = []
    for (corr_ticker, day), fix in corrections.items():
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
            total_return.iloc[i] = (df['Close'].iloc[i] + fix) / df['Close'].iloc[i - 1] - 1
        handled_days.append(day)

    # one-day spikes: the whole two-day move goes on the second day
    for i in find_spikes(total_return):
        two_day = (1 + total_return.iloc[i]) * (1 + total_return.iloc[i + 1]) - 1
        total_return.iloc[i] = 0.0
        total_return.iloc[i + 1] = two_day
        handled_days += [df.index[i], df.index[i + 1]]
        flags_log.append(dict(market=market, ticker=ticker, date=df.index[i].date(),
                              type='one-day spike merged'))

    # other large gaps: keep Yahoo's adjusted return, but list them for checking
    gap = (total_return - raw_return).abs()
    for day in df.index[gap > FLAG_THRESHOLD]:
        if day not in handled_days:
            flags_log.append(dict(market=market, ticker=ticker, date=day.date(),
                                  type='UNVERIFIED - Yahoo adjusted kept',
                                  raw_return=raw_return[day], adj_return=total_return[day]))
    df['ret'] = total_return

    # inputs of the Abdi-Ranaldo spread estimator (range widened only if the close is outside it)
    high = df[['High', 'Close']].max(axis=1)
    low = df[['Low', 'Close']].min(axis=1)
    df['c'] = np.log(df['Close'])
    df['eta'] = (np.log(high) + np.log(low)) / 2
    return df


def to_monthly(df, trading_days):
    """One row per calendar month: price, signals, next return, liquidity, traded value, spread."""
    month = df.index.to_period('M')
    price = (1 + df['ret'].fillna(0)).cumprod()
    calendar = pd.period_range(month.min(), month.max(), freq='M')
    m = pd.DataFrame(index=calendar)

    # a month without trades keeps the last price (also covers the Athens closure of July 2015)
    m['P'] = price.groupby(month).last().reindex(calendar).ffill()
    m['days'] = df.groupby(month).size().reindex(calendar).fillna(0)
    m['value'] = (df['Close'] * df['Volume']).groupby(month).sum().reindex(calendar).fillna(0)

    # Abdi-Ranaldo spread per month, averaged over months t-2..t
    eta_next_day = df['eta'].groupby(month).shift(-1)
    product = (df['c'] - df['eta']) * (df['c'] - eta_next_day)
    m['spread'] = np.sqrt((4 * product.groupby(month).mean()).clip(lower=0)).reindex(calendar)
    m['spread'] = m['spread'].rolling(3, min_periods=1).mean()

    days_open = trading_days.reindex(calendar)
    m['liquid'] = (m['days'] / days_open >= MIN_TRADED).fillna(False)
    # 12-month average daily traded value over months in which the exchange was open
    avg_daily_value = (m['value'] / days_open).dropna()
    m['adv_12m'] = avg_daily_value.rolling(12, min_periods=12).mean().reindex(calendar)

    P = m['P']
    m['ret_1m'] = P / P.shift(1) - 1
    for J in [3, 6, 12]:
        m[f'trail_{J}m'] = P / P.shift(J) - 1
    m['trail_12_1m'] = P.shift(1) / P.shift(12) - 1
    m['next_1m'] = m['ret_1m'].shift(-1)
    return m


def load_market(market, config, flags_log):
    daily = {}
    for ticker in config['tickers']:
        if os.path.exists(os.path.join('data', market, f'{ticker}.csv')):
            data = load_stock(market, ticker, config['corrections'], flags_log)
            if data is not None:
                daily[ticker] = data
    # the exchange is "open" on every day on which at least one of its stocks traded
    all_days = pd.Index(sorted(set().union(*[d.index for d in daily.values()])))
    trading_days = pd.Series(1, index=all_days).groupby(all_days.to_period('M')).sum()
    return {ticker: to_monthly(d, trading_days) for ticker, d in daily.items()}


def universe(stocks, k):
    """Keep each month only the k most liquid eligible stocks (others get blank signals)."""
    traded_value = pd.DataFrame({t: m['adv_12m'] for t, m in stocks.items()})
    eligible = pd.DataFrame({t: m['liquid'] & m['adv_12m'].notna() & m[MAIN].notna()
                             for t, m in stocks.items()}).reindex(traded_value.index).fillna(False)
    member = traded_value.where(eligible).rank(axis=1, ascending=False) <= k

    restricted = {}
    for ticker, m in stocks.items():
        m = m.copy()
        inside = member[ticker].reindex(m.index).fillna(False).astype(bool)
        m.loc[~inside, SIGNALS] = np.nan
        restricted[ticker] = m
    return restricted, member


# =============================================================================
# Portfolios
# =============================================================================

def realized_returns(next_returns_row, chosen):
    r = next_returns_row.reindex(list(chosen))
    for ticker in r.index[r.isna()]:
        MISSING_LOG.append((next_returns_row.name, ticker))
    return r.fillna(0.0)


def leg_returns(stocks, signal):
    """Monthly returns of the winners, the losers and all ranked stocks."""
    signals = pd.DataFrame({t: m[signal] for t, m in stocks.items()})
    next_returns = pd.DataFrame({t: m['next_1m'] for t, m in stocks.items()})
    rows = {}
    for month in signals.index:
        if next_returns.loc[month].isna().all():          # last month: nothing earned yet
            continue
        ranked = signals.loc[month].dropna().sort_values()   # known at t only
        n = max(2, int(round(len(ranked) * FRACTION)))
        if len(ranked) < 2 * n:
            continue
        r = realized_returns(next_returns.loc[month], ranked.index)
        rows[month] = dict(winners=r[ranked.index[-n:]].mean(), losers=r[ranked.index[:n]].mean(),
                           all=r.mean(), n_stocks=len(ranked))
    return pd.DataFrame(rows).T.sort_index()


def costed_portfolio(stocks, signal, drop_losers):
    """All ranked stocks in equal weights (optionally without the bottom 30%), after costs.
    Cost per leu traded = half the estimated spread + COMMISSION; the spread used at month t
    is known at t (if missing: the stock's median up to t, else 2%)."""
    signals = pd.DataFrame({t: m[signal] for t, m in stocks.items()})
    next_returns = pd.DataFrame({t: m['next_1m'] for t, m in stocks.items()})
    spreads = pd.DataFrame({t: m['spread'] for t, m in stocks.items()})

    gross, costs = {}, {}
    drifted = pd.Series(dtype=float)
    for month in signals.index:
        if next_returns.loc[month].isna().all():
            continue
        ranked = signals.loc[month].dropna().sort_values()
        n = max(2, int(round(len(ranked) * FRACTION)))
        if len(ranked) < 2 * n:
            continue
        chosen = ranked.index[n:] if drop_losers else ranked.index
        weights = pd.Series(1 / len(chosen), index=chosen)

        names = weights.index.union(drifted.index)
        weight_change = (weights.reindex(names, fill_value=0) - drifted.reindex(names, fill_value=0)).abs()
        median_so_far = spreads.loc[:month].median()
        spread = spreads.loc[month, names].fillna(median_so_far.reindex(names)).fillna(FALLBACK_SPREAD)
        costs[month] = (weight_change * (0.5 * spread + COMMISSION)).sum()

        r = realized_returns(next_returns.loc[month], chosen)
        gross[month] = (weights * r).sum()
        drifted = weights * (1 + r) / (weights * (1 + r)).sum()
    return pd.Series(gross) - pd.Series(costs), pd.Series(costs)


# =============================================================================
# Run
# =============================================================================

if __name__ == '__main__':
    pd.set_option('display.width', 230)
    pd.set_option('display.max_rows', 300)

    flags_log, rows_A, rows_B, rows_C, rows_D, rows_desc = [], [], [], [], [], []
    loser_effect, avoid_vs_all_paths = {}, {}

    for market, config in MARKETS.items():
        stocks = load_market(market, config, flags_log)
        stocks_15, member = universe(stocks, K_UNIVERSE)

        # description of the market
        size = member.sum(axis=1)
        size = size[size > 0]
        ever_in = [t for t in member.columns if member[t].any()]
        median_spread = np.nanmedian([
            stocks_15[t]['spread'][member[t].reindex(stocks_15[t].index).fillna(False).astype(bool)].median()
            for t in ever_in])
        rows_desc.append(dict(market=market, level=config['level'], stocks_with_data=len(stocks),
                              stocks_ever_in_universe=len(ever_in), avg_universe_size=size.mean(),
                              first_month=str(size.index.min()), median_spread_universe=median_spread))

        # A) and B), D)
        months = None
        for k, universe_stocks in [(K_UNIVERSE, stocks_15), (K_ROBUST, universe(stocks, K_ROBUST)[0])]:
            for signal in SIGNALS:
                legs = leg_returns(universe_stocks, signal)
                annual, t, p, n = mean_test(legs['winners'] - legs['losers'])
                rows_A.append(dict(market=market, level=config['level'], universe=f'top {k}', signal=signal,
                                   WML_annual=annual, t_NW=t, p=p, sig=stars(p), months=n))
                if signal != MAIN:
                    continue
                for leg, x in [('winners - all', legs['winners'] - legs['all']),
                               ('all - losers', legs['all'] - legs['losers'])]:
                    annual, t, p, n = mean_test(x)
                    rows_B.append(dict(market=market, level=config['level'], universe=f'top {k}', leg=leg,
                                       annual=annual, t_NW=t, p=p, sig=stars(p), months=n,
                                       pct_positive=(x > 0).mean()))
                if k == K_UNIVERSE:
                    loser_effect[market] = legs['all'] - legs['losers']
                    months = legs.index
                    # calendar years: the return of formation month t is earned in month t+1
                    both = legs[['losers', 'all']].astype(float)
                    yearly = (1 + both).groupby((both.index + 1).year).prod() - 1
                    lagged = yearly['losers'] < yearly['all']
                    rows_D.append(dict(market=market, level=config['level'], years=len(lagged),
                                       years_losers_lagged=int(lagged.sum()),
                                       **{str(year): round(gap, 3)
                                          for year, gap in (yearly['all'] - yearly['losers']).items()}))

        # C) avoid-losers after costs
        rf = pd.Series(monthly_rf(config['rates'], months + 1), index=months)
        everyone, everyone_cost = costed_portfolio(stocks_15, MAIN, drop_losers=False)
        avoid, avoid_cost = costed_portfolio(stocks_15, MAIN, drop_losers=True)
        everyone, avoid = everyone.reindex(months), avoid.reindex(months)
        alpha, t, p = alpha_against(avoid, everyone, rf)
        rows_C.append(dict(market=market, level=config['level'], portfolio='avoid losers (drop bottom 30%)',
                           **performance(avoid, rf), alpha_vs_EW=alpha, t_alpha=t, p_alpha=p, sig=stars(p),
                           annual_cost=avoid_cost.mean() * 12))
        rows_C.append(dict(market=market, level=config['level'], portfolio='equal-weight all',
                           **performance(everyone, rf), annual_cost=everyone_cost.mean() * 12))
        relative = (1 + avoid).cumprod() / (1 + everyone).cumprod()
        relative.index = (relative.index + 1).to_timestamp()        # shown at the month earned
        avoid_vs_all_paths[market] = relative
        print(f'{market}: done ({len(stocks)} stocks with data)')

    desc, A, B, C, D = map(pd.DataFrame, [rows_desc, rows_A, rows_B, rows_C, rows_D])
    flags = pd.DataFrame(flags_log)

    # Holm adjustment across the four markets for the two key tests (15-stock universe)
    main_wml = (A['universe'] == f'top {K_UNIVERSE}') & (A['signal'] == MAIN)
    main_losers = (B['universe'] == f'top {K_UNIVERSE}') & (B['leg'] == 'all - losers')
    A.loc[main_wml, 'p_holm_4_markets'] = holm(A.loc[main_wml, 'p'])
    B.loc[main_losers, 'p_holm_4_markets'] = holm(B.loc[main_losers, 'p'])

    # E) each market's loser effect minus Germany's, over the same months
    E = []
    germany = loser_effect.get('Germany')
    for market, x in loser_effect.items():
        if market == 'Germany' or germany is None:
            continue
        both = pd.concat([x, germany], axis=1).dropna()
        annual, t, p, n = mean_test(both.iloc[:, 0] - both.iloc[:, 1])
        E.append(dict(market=market, comparison='loser effect minus Germany', difference_annual=annual,
                      t_NW=t, p=p, sig=stars(p), months=n))
    E = pd.DataFrame(E)

    for title, df in [('Descriptive', desc), ('A) Winners minus losers', A),
                      ('B) Winners vs losers legs (12-1)', B), ('C) Avoid-losers after stock-specific costs', C),
                      ('D) Years in which losers lagged', D), ('E) Loser effect relative to Germany', E),
                      ('Data flags', flags)]:
        print(f'\n=== {title} ===')
        print(df.round(4).to_string(index=False) if len(df) else '(none)')

    # Figure 6: effects with 95% intervals, markets ordered by level of development
    order = sorted(MARKETS, key=lambda name: MARKETS[name]['level'])
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x_positions = np.arange(len(order))
    bars = [('Winners minus losers', A[main_wml], 'WML_annual', '#3182bd'),
            ('All stocks minus losers', B[main_losers], 'annual', '#9ecae1')]
    for j, (label, frame, column, color) in enumerate(bars):
        table = frame.set_index('market').reindex(order)
        estimate = table[column] * 100
        standard_error = estimate / table['t_NW']
        ax.bar(x_positions + (j - 0.5) * 0.38, estimate, 0.38, yerr=1.96 * standard_error.abs(),
               capsize=4, label=label, color=color)
    ax.axhline(0, color='black', lw=0.8)
    ax.set_xticks(x_positions)
    ax.set_xticklabels([f"{name}\n(level {MARKETS[name]['level']})" for name in order])
    ax.set_ylabel('% per year')
    ax.grid(axis='y', alpha=0.3)
    ax.set_title('Momentum and the loser effect across markets (12-1 signal, 95% intervals)')
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig('markets_effects.png', dpi=200)
    plt.close(fig)

    # Figure 7: value of avoiding losers over time
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for name in order:
        path = avoid_vs_all_paths[name]
        ax.plot(path.index, path.values, label=name)
    ax.axhline(1, color='black', lw=0.8)
    ax.set_ylabel('Avoid-losers / equal-weight (growth of 1)')
    ax.grid(axis='y', alpha=0.3)
    ax.set_title('Value of avoiding losers in each market, after costs')
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig('markets_avoid_losers.png', dpi=200)
    plt.close(fig)

    with pd.ExcelWriter('markets_results.xlsx') as xw:
        for name, df in [('descriptive', desc), ('A_wml', A), ('B_legs', B), ('C_avoid_losers', C),
                         ('D_yearly', D), ('E_vs_Germany', E), ('data_flags', flags)]:
            df.to_excel(xw, sheet_name=name, index=False)
    print('\nSaved markets_results.xlsx, markets_effects.png and markets_avoid_losers.png')
