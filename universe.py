"""
universe.py - the rule-based universe (reduces survivorship and selection bias).

Each month t, the universe is the 15 most liquid stocks of the 32-stock pool, ranked by
average daily traded value over months t-11..t. Only stocks with 12 months of history
that traded on >= 80% of the days in month t are eligible. Everything uses information
available at the end of month t (the rules are in common.py: load_pool, membership).

All tests are rerun inside this universe and compared with the fixed 13 stocks.
Saves universe.xlsx and universe_chart.png (paper Tables 3, 5 and A1).
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from common import (SIGNALS, MAIN, K_MAIN, BASE_COST, load_pool, membership, restrict,
                    fixed_universe, rf_for_holding_month, evaluate, summarize, print_table,
                    save_fig, wealth_path, log_axis_in_multiples)
from portfolios import wml_series, portfolio, top_n

K_LIST = [10, 15, 20]   # universe sizes tested


def long_only_rows(stocks, index_m, label):
    """Winners, equal-weight, losers and Top 1-4 after the baseline cost."""
    winners = portfolio(stocks, MAIN, 'winners')
    everyone = portfolio(stocks, MAIN, 'all')
    losers = portfolio(stocks, MAIN, 'losers')

    months = winners.returns.index
    bet = index_m['next_1m'].reindex(months)
    rf = rf_for_holding_month(months)

    def net(p):
        return (p.returns - BASE_COST * p.turnover).reindex(months)

    rows = [evaluate(net(winners), bet, rf, f'{label}: winners top 30%', winners.turnover),
            evaluate(net(everyone), bet, rf, f'{label}: equal-weight all', everyone.turnover),
            evaluate(net(losers), bet, rf, f'{label}: losers bottom 30%', losers.turnover)]
    for n in [1, 2, 3, 4]:
        p = top_n(stocks, MAIN, n)
        rows.append(evaluate(net(p), bet, rf, f'{label}: top {n}', p.turnover))
    return rows, winners.returns - BASE_COST * winners.turnover


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    pd.set_option('display.max_rows', 200)

    index_m, pool = load_pool()
    print(f'\nPool: {len(pool)} stocks with data')

    member = membership(pool, K_MAIN)
    rule_based = restrict(pool, member)
    fixed = fixed_universe(pool)

    # 1) which stocks enter the universe, and how often?
    months_in = member.sum().sort_values(ascending=False)
    first_month_in = member.idxmax().where(member.any())        # first True in each column
    who = pd.DataFrame({'months_in_universe': months_in,
                        'first_month_in': first_month_in.reindex(months_in.index).astype(str),
                        'in_fixed_13': [t in fixed for t in months_in.index]})
    who = who[who['months_in_universe'] > 0]
    size = member.sum(axis=1)
    print(f'\n=== 1) Rule-based universe (top {K_MAIN} by 12-month traded value) ===')
    print(f'Stocks per month: min {size[size > 0].min()}, max {size.max()}; '
          f'{len(who)} different stocks were in the universe at some point')
    print(who.to_string())

    # 2) winners minus losers for universes of 10, 15 and 20 stocks
    rows = []
    for k in K_LIST:
        universe_k = restrict(pool, membership(pool, k))
        for signal in SIGNALS:
            rows.append({'universe': f'rule-based top {k}',
                         **summarize(wml_series(universe_k, signal), signal)})
            rows.append({'universe': f'rule-based top {k}',
                         **summarize(wml_series(universe_k, signal, sector_neutral=True),
                                     f'{signal} sector-neutral')})
    for signal in SIGNALS:
        rows.append({'universe': 'fixed 13', **summarize(wml_series(fixed, signal), signal)})
    wml = pd.DataFrame(rows)
    print_table('2) Winners minus losers (top 30% - bottom 30%)', wml)

    # 3) long-only portfolios: rule-based vs fixed
    rows_rule, winners_rule = long_only_rows(rule_based, index_m, f'Rule-based {K_MAIN}')
    rows_fixed, winners_fixed = long_only_rows(fixed, index_m, 'Fixed 13')
    months = winners_rule.index.intersection(winners_fixed.index)
    bet = index_m['next_1m'].reindex(months)
    rf = rf_for_holding_month(months)
    long_only = pd.DataFrame(rows_rule + rows_fixed + [evaluate(bet, bet, rf, 'BET-TR')])
    print_table(f'3) Long-only portfolios after {BASE_COST:.1%} cost', long_only, 3)

    # chart
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for series, name, style in [(winners_rule.reindex(months), f'Winners, rule-based top {K_MAIN}', '-'),
                                (winners_fixed.reindex(months), 'Winners, fixed 13 stocks', '--')]:
        path = wealth_path(series)
        ax.plot(path.index, path.values, label=name, linestyle=style)
    path = wealth_path(bet)
    ax.plot(path.index, path.values, label='BET-TR', color='black')
    log_axis_in_multiples(ax)
    ax.set_ylabel('Value of 1 leu invested (log scale)')
    ax.set_title(f'Long-only momentum: rule-based vs fixed universe ({BASE_COST:.1%} cost)')
    ax.legend()
    fig.tight_layout()
    save_fig(fig, 'universe_chart.png')

    with pd.ExcelWriter('universe.xlsx') as xw:
        who.reset_index(names='ticker').to_excel(xw, sheet_name='1_membership', index=False)
        wml.to_excel(xw, sheet_name='2_wml', index=False)
        long_only.to_excel(xw, sheet_name='3_long_only', index=False)
        member.astype(int).reset_index(names='month').to_excel(xw, sheet_name='monthly_members', index=False)
    print('\nSaved universe.xlsx and universe_chart.png')
