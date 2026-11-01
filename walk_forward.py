"""
walk_forward.py - out-of-sample test of the strategy choice (paper Table 6, Figure 3).

Question: if an investor had to CHOOSE how many winners to hold and which look-back to
use, using only the past, would the strategy still beat the index?

16 candidate strategies: Top 1/2/3/4 x signal 3m / 6m / 12m / 12-1m, after 0.5% costs.

At the end of January of each year (when the first portfolio of the year is formed), pick
the candidate with the best Sharpe ratio over the past and use it for that year's
portfolios. All training returns are already known at that moment: the last one, from
the portfolio formed in December, is earned during January.
  - expanding window: all previous years
  - rolling window  : only the previous 3 years
  - single split    : choose on 2016-2020, test on 2021-2025

Saves walk_forward.xlsx and walk_forward_chart_fixed/rule-based.png.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (MAIN, K_MAIN, BASE_COST, load_pool, fixed_universe, rule_based_universe,
                    rf_for_holding_month, evaluate, calendar_year_returns, save_fig,
                    wealth_path, log_axis_in_multiples)
from portfolios import portfolio, top_n

GRID_N = [1, 2, 3, 4]
GRID_SIGNALS = ['trail_3m', 'trail_6m', 'trail_12m', 'trail_12_1m']
MIN_TRAIN_YEARS = 2      # the first two years (2016, 2017) are only used for training
ROLLING_YEARS = 3


def grid_returns(stocks, months):
    """Net monthly returns of all 16 candidate strategies, one column each."""
    columns = {}
    for signal in GRID_SIGNALS:
        for n in GRID_N:
            p = top_n(stocks, signal, n)
            columns[f'Top {n} | {signal}'] = (p.returns - BASE_COST * p.turnover).reindex(months)
    return pd.DataFrame(columns)


def sharpe(r, rf):
    excess = (r - rf).dropna()
    if len(excess) <= 2:
        return np.nan
    return excess.mean() / excess.std() * np.sqrt(12)


def walk_forward(candidates, rf, window=None):
    """For each test year, choose the candidate with the best past Sharpe ratio.

    candidates: months (formation months) x strategies table of net returns.
    The training set for year y = formation months of the years before y (only the last
    `window` years if a window is given). The test = formation months of year y.
    """
    years = sorted(set(candidates.index.year))
    chosen_returns, log = [], []
    for year in years[MIN_TRAIN_YEARS:]:
        train = candidates[candidates.index.year < year]
        if window:
            train = train[train.index.year >= year - window]

        scores = train.apply(lambda strategy: sharpe(strategy, rf.reindex(train.index)))
        best = scores.idxmax()

        test = candidates.loc[candidates.index.year == year, best]
        chosen_returns.append(test)
        log.append(dict(year=year, chosen=best, train_sharpe=scores[best],
                        return_that_year=(1 + test).prod() - 1))
    return pd.concat(chosen_returns), pd.DataFrame(log)


def run(stocks, index_m, label):
    print(f'\n\n################ {label.upper()} ################')
    winners = portfolio(stocks, MAIN, 'winners')
    months = winners.returns.index
    winners_net = winners.returns - BASE_COST * winners.turnover

    candidates = grid_returns(stocks, months)
    rf = rf_for_holding_month(months)
    bet = index_m['next_1m'].reindex(months)

    wf_expanding, log_expanding = walk_forward(candidates, rf)
    wf_rolling, log_rolling = walk_forward(candidates, rf, window=ROLLING_YEARS)
    oos = wf_expanding.index                       # out-of-sample months (from year 3)

    # reference only: the best strategy chosen with hindsight (uses the whole sample)
    hindsight = candidates.apply(lambda strategy: sharpe(strategy, rf)).idxmax()

    print('\n=== 1) Walk-forward choices (expanding window) ===')
    print(log_expanding.round(3).to_string(index=False))
    print(f'\n=== 1b) Walk-forward choices (rolling {ROLLING_YEARS}-year window) ===')
    print(log_rolling.round(3).to_string(index=False))

    b, r = bet.reindex(oos), rf.reindex(oos)
    comparison = pd.DataFrame([
        evaluate(wf_expanding, b, r, 'Walk-forward, expanding window'),
        evaluate(wf_rolling.reindex(oos), b, r, f'Walk-forward, rolling {ROLLING_YEARS}y'),
        evaluate(winners_net.reindex(oos), b, r, 'Pre-specified: top 30%, 12-1'),
        evaluate(candidates['Top 2 | trail_12_1m'].reindex(oos), b, r, 'Top 2, 12-1'),
        evaluate(candidates[hindsight].reindex(oos), b, r, f'Hindsight best ({hindsight}) - look-ahead!'),
        evaluate(b, b, r, 'BET-TR'),
    ]).drop(columns=['annual_turnover'])
    print(f'\n=== 2) Out-of-sample comparison, {oos.min()} to {oos.max()} ===')
    print(comparison.round(3).to_string(index=False))

    # single split: choose on portfolios formed in 2016-2020, test on 2021-2025
    first = candidates[candidates.index.year <= 2020]
    second = candidates[candidates.index.year >= 2021]
    pick = first.apply(lambda strategy: sharpe(strategy, rf.reindex(first.index))).idxmax()
    b2, r2 = bet.reindex(second.index), rf.reindex(second.index)
    split = pd.DataFrame([
        evaluate(second[pick], b2, r2, f'Chosen on 2016-2020: {pick}'),
        evaluate(second['Top 4 | trail_12_1m'], b2, r2, 'Top 4, 12-1'),
        evaluate(b2, b2, r2, 'BET-TR'),
    ]).drop(columns=['annual_turnover'])
    print('\n=== 3) Single split: choose on 2016-2020, test on 2021-2025 ===')
    print(split.round(3).to_string(index=False))

    # calendar years (the year in which each return is earned)
    yearly = calendar_year_returns(pd.DataFrame({'Walk-forward': wf_expanding,
                                                 'Pre-specified top 30%': winners_net.reindex(oos),
                                                 'BET-TR': b}))
    print('\n=== 4) Calendar-year returns (out-of-sample years) ===')
    print(yearly.round(3).to_string())

    # chart
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for series, name, style, color in [(wf_expanding, 'Walk-forward (expanding)', '-', None),
                                       (winners_net.reindex(oos), 'Pre-specified top 30%', '--', None),
                                       (b, 'BET-TR', '-', 'black')]:
        path = wealth_path(series)
        ax.plot(path.index, path.values, label=name, linestyle=style, color=color)
    log_axis_in_multiples(ax)
    ax.set_ylabel('Value of 1 leu invested (log scale)')
    ax.set_title(f'Walk-forward test (exploratory), {label} ({BASE_COST:.1%} cost)')
    ax.legend()
    fig.tight_layout()
    tag = label.split()[0].lower()
    save_fig(fig, f'walk_forward_chart_{tag}.png')
    plt.close(fig)

    return {f'{tag}_choices': log_expanding, f'{tag}_choices_rolling': log_rolling,
            f'{tag}_oos': comparison, f'{tag}_split': split,
            f'{tag}_yearly': yearly.reset_index(names='year')}


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    index_m, pool = load_pool()

    sheets = {}
    sheets.update(run(fixed_universe(pool), index_m, 'Fixed 13 stocks'))
    sheets.update(run(rule_based_universe(pool), index_m, f'Rule-based top {K_MAIN}'))

    with pd.ExcelWriter('walk_forward.xlsx') as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
    print('\nSaved walk_forward.xlsx and the charts')
