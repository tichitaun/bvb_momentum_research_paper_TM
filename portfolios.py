"""
portfolios.py - how stocks are ranked and how portfolios are built, month by month.

Every function follows the same timing rule:
    at the end of month t, rank the stocks using ONLY their signal (known at t),
    choose the stocks, then earn their return over month t+1 (next_1m).
Whether a stock can be chosen never depends on its future return.
"""
from collections import namedtuple

import pandas as pd

from common import FRACTION, SECTORS, monthly_rf

MISSING_LOG = []   # (formation month, ticker): a chosen stock had no next-month return
SKIPPED = []       # formation months in which no portfolio could be formed after the start


# =============================================================================
# Small helpers
# =============================================================================

def signal_table(stocks, signal):
    """Months x stocks table of the chosen signal (e.g. trail_12_1m)."""
    return pd.DataFrame({ticker: m[signal] for ticker, m in stocks.items()})


def next_return_table(stocks):
    """Months x stocks table of the next-month return (next_1m)."""
    return pd.DataFrame({ticker: m['next_1m'] for ticker, m in stocks.items()})


def number_per_side(n_stocks):
    """How many stocks go into the winner (and the loser) group: 30%, at least 2.

    Python rounds .5 to the nearest even number, e.g. 15 stocks -> round(4.5) = 4.
    """
    return max(2, int(round(n_stocks * FRACTION)))


def is_end_of_sample(next_returns_row):
    """True in the last formation month: no next-month return exists yet for any stock."""
    return next_returns_row.isna().all()


def realized_returns(next_returns_row, chosen):
    """Next-month returns of the CHOSEN stocks.

    If a chosen stock has no return (it stopped trading), it is logged and gets 0%
    (its price is carried forward). In our data this never happens.
    """
    r = next_returns_row.reindex(list(chosen))
    for ticker in r.index[r.isna()]:
        MISSING_LOG.append((next_returns_row.name, ticker))
    return r.fillna(0.0)


def subtract_sector_average(table):
    """For every month, subtract each sector's average from the stocks of that sector.

    After this, a stock is "high" only if it beat the other stocks of its own sector.
    Missing values are ignored when computing the average.
    """
    table = table.copy()
    sector_of = pd.Series({ticker: SECTORS[ticker] for ticker in table.columns})
    for sector in sector_of.unique():
        columns = list(sector_of[sector_of == sector].index)
        sector_average = table[columns].mean(axis=1)
        table[columns] = table[columns].sub(sector_average, axis=0)
    return table


# =============================================================================
# 1. Winners minus losers (the main test)
# =============================================================================

def wml_series(stocks, signal, sector_neutral=False, drop=None, return_sizes=False):
    """Monthly return of (top 30% by signal) minus (bottom 30% by signal), equal weights.

    sector_neutral : rank on the signal minus the sector average, and compare returns
                     minus the sector average (only stocks ranked that month count)
    drop           : a ticker to leave out (leave-one-out test)
    """
    tickers = [t for t in stocks if t != drop]
    signals = signal_table({t: stocks[t] for t in tickers}, signal)
    next_returns = next_return_table({t: stocks[t] for t in tickers})

    if sector_neutral:
        next_returns = next_returns.where(signals.notna())     # only ranked stocks count
        signals = subtract_sector_average(signals)
        next_returns = subtract_sector_average(next_returns)

    wml, n_ranked = {}, {}
    for month in signals.index:
        if is_end_of_sample(next_returns.loc[month]):
            continue
        ranked = signals.loc[month].dropna().sort_values()      # lowest signal first
        n = number_per_side(len(ranked))
        if len(ranked) < 2 * n:                                  # not enough stocks yet
            continue
        losers, winners = ranked.index[:n], ranked.index[-n:]
        r = realized_returns(next_returns.loc[month], ranked.index)
        wml[month] = r[winners].mean() - r[losers].mean()
        n_ranked[month] = len(ranked)

    wml = pd.Series(wml, dtype=float).sort_index()
    if return_sizes:
        return wml, pd.Series(n_ranked)
    return wml


def leg_returns(stocks, signal, sector_neutral=False):
    """Monthly returns of the winners, the losers and all ranked stocks (equal weights).

    Used to split winners-minus-losers into (winners - all) + (all - losers).
    With sector_neutral=True the RANKING uses the signal minus its sector average, but the
    returns are the stocks' own returns.
    """
    signals = signal_table(stocks, signal)
    next_returns = next_return_table(stocks)
    ranking_signal = subtract_sector_average(signals) if sector_neutral else signals

    rows = {}
    for month in signals.index:
        if is_end_of_sample(next_returns.loc[month]):
            continue
        ranked = ranking_signal.loc[month].dropna().sort_values()
        n = number_per_side(len(ranked))
        if len(ranked) < 2 * n:
            continue
        r = realized_returns(next_returns.loc[month], ranked.index)
        rows[month] = dict(winners=r[ranked.index[-n:]].mean(),
                           losers=r[ranked.index[:n]].mean(),
                           all=r[ranked.index].mean())
    return pd.DataFrame(rows).T.sort_index()


# =============================================================================
# 2. Investable portfolios (long-only), with turnover for trading costs
# =============================================================================

Portfolio = namedtuple('Portfolio', ['returns', 'turnover', 'holdings', 'trades'])


def build_portfolio(stocks, signal, choose, cash_earns_rf=False):
    """Run a monthly long-only strategy.

    choose(ranked) receives the stocks with a signal at month t, sorted from lowest to
    highest signal, and returns (chosen tickers, weight of each) or None if it cannot
    form a portfolio that month.

    Each month:
      1. choose the stocks and give each its weight (the rest, if any, is cash)
      2. turnover = how much must be bought or sold to go from last month's DRIFTED
         weights to the new weights:  sum |new weight - drifted weight|
      3. return over month t+1 = sum(weight x stock return) + cash x risk-free rate
      4. drifted weights for next month: each stock grows with its own return
    Returns are GROSS (before costs); costs are charged later as cost x turnover.
    """
    signals = signal_table(stocks, signal)
    next_returns = next_return_table(stocks)

    returns, turnover, holdings, trades = {}, {}, {}, {}
    drifted = pd.Series(dtype=float)              # weights just before rebalancing

    for month in signals.index:
        if is_end_of_sample(next_returns.loc[month]):
            continue
        ranked = signals.loc[month].dropna().sort_values()
        choice = choose(ranked)
        if choice is None:
            if returns:                           # a gap after the strategy has started
                SKIPPED.append(month)
            continue
        chosen, weight_each = choice

        # 1. target weights
        weights = pd.Series(weight_each, index=chosen, dtype=float)
        cash = 1 - weights.sum() if cash_earns_rf else 0.0
        rf = monthly_rf(pd.PeriodIndex([month + 1]))[0] if cash_earns_rf else 0.0

        # 2. turnover
        names = weights.index.union(drifted.index)
        change = (weights.reindex(names, fill_value=0) - drifted.reindex(names, fill_value=0)).abs()
        turnover[month] = change.sum()
        trades[month] = change[change > 1e-9]

        # 3. return earned over month t+1
        r = realized_returns(next_returns.loc[month], chosen) if len(chosen) else pd.Series(dtype=float)
        returns[month] = (weights * r).sum() + cash * rf
        holdings[month] = ', '.join(sorted(chosen)) if len(chosen) else 'cash'

        # 4. weights drift with prices until the next rebalancing
        grown = weights * (1 + r)
        if cash_earns_rf:
            drifted = grown / (grown.sum() + cash * (1 + rf))
        else:
            drifted = grown / grown.sum()

    return Portfolio(pd.Series(returns), pd.Series(turnover), pd.Series(holdings), trades)


# ---- ways of choosing stocks -------------------------------------------------

def choose_group(group):
    """'winners' = top 30%, 'losers' = bottom 30%, 'all' = every ranked stock."""
    def choose(ranked):
        n = number_per_side(len(ranked))
        if len(ranked) < 2 * n:
            return None
        if group == 'winners':
            chosen = ranked.index[-n:]
        elif group == 'losers':
            chosen = ranked.index[:n]
        else:
            chosen = ranked.index
        return chosen, 1 / len(chosen)
    return choose


def choose_top(n, only_if_positive=False):
    """The n stocks with the highest signal, 1/n each. With only_if_positive, a stock whose
    own past return is not positive is replaced by cash (absolute momentum filter)."""
    def choose(ranked):
        if len(ranked) < 2 * n:                   # winners may be at most half the stocks
            return None
        chosen = list(ranked.index[-n:])
        if only_if_positive:
            chosen = [t for t in chosen if ranked[t] > 0]
        return chosen, 1 / n
    return choose


def choose_all_except_losers(n_drop):
    """All ranked stocks except the worst ones, equal weights.
    n_drop = 'frac' drops the bottom 30% (the loser group); a number drops that many."""
    def choose(ranked):
        n = number_per_side(len(ranked))
        if len(ranked) < 2 * n:
            return None
        drop = n if n_drop == 'frac' else n_drop
        chosen = ranked.index[drop:]
        return chosen, 1 / len(chosen)
    return choose


# ---- shortcuts used by the scripts ------------------------------------------

def portfolio(stocks, signal, group):
    """Winners, losers or all stocks, equal weights."""
    return build_portfolio(stocks, signal, choose_group(group))


def top_n(stocks, signal, n, abs_filter=False):
    """The n strongest winners; empty slots (with the filter) earn the risk-free rate."""
    return build_portfolio(stocks, signal, choose_top(n, abs_filter), cash_earns_rf=True)


def avoid_losers(stocks, signal, n_drop='frac'):
    """All stocks except the losers."""
    return build_portfolio(stocks, signal, choose_all_except_losers(n_drop))
