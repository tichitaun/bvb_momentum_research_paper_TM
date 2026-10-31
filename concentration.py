"""
concentration.py - how many winners should you hold? (paper Table 5)

Top 1, 2, 3 or 4 stocks by 12-1 return, equal weights, rebalanced monthly. Each is run
twice: normally, and "with filter" (a winner is held only if its own past return was
positive; otherwise that part of the money stays in cash at the BNR rate).

Saves concentration.xlsx and concentration_chart_core/extended.png.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from common import (UNIVERSES, MAIN, BASE_COST, load_all, rf_for_holding_month, evaluate,
                    calendar_year_returns, print_table, save_fig, wealth_path,
                    log_axis_in_multiples)
from portfolios import top_n

N_HOLD = [1, 2, 3, 4]


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    index_m, all_stocks = load_all()
    sheets = {}

    for label, tickers in UNIVERSES.items():
        stocks = {t: all_stocks[t] for t in tickers if t in all_stocks}
        print(f'\n\n################ {label.upper()} UNIVERSE: {len(stocks)} stocks ################')

        # winners may be at most half of the stocks, so the core 7 only goes up to Top 3
        n_list = [n for n in N_HOLD if 2 * n <= len(stocks)]

        net_returns, holdings = {}, {}
        for with_filter in [False, True]:
            for n in n_list:
                p = top_n(stocks, MAIN, n, abs_filter=with_filter)
                name = f'Top {n}' + (' + filter' if with_filter else '')
                net_returns[name] = p.returns - BASE_COST * p.turnover
                holdings[name] = p.holdings

        # compare every portfolio over exactly the same months
        common_months = set.intersection(*[set(r.index) for r in net_returns.values()])
        months = pd.PeriodIndex(sorted(common_months), freq='M')
        bet = index_m['next_1m'].reindex(months)
        rf = rf_for_holding_month(months)

        rows = []
        for name, r in net_returns.items():
            row = evaluate(r.reindex(months), bet, rf, name)
            row['pct_months_in_cash'] = (holdings[name].reindex(months) == 'cash').mean()
            rows.append(row)
        rows.append(evaluate(bet, bet, rf, 'BET-TR (buy and hold)'))
        table = pd.DataFrame(rows).drop(columns=['annual_turnover'])
        print_table(f'Top-N winners ({MAIN}), after {BASE_COST:.1%} trading cost', table, 3)

        # calendar years
        by_year = pd.DataFrame({f'Top {n}': net_returns[f'Top {n}'].reindex(months) for n in n_list})
        by_year['BET-TR'] = bet
        yearly = calendar_year_returns(by_year)
        print('\n=== Calendar-year returns ===')
        print(yearly.round(3).to_string())

        # which stock did Top 1 hold, and for how many months?
        print('\n=== Top 1: months each stock was the single holding ===')
        print(holdings['Top 1'].reindex(months).value_counts().to_string())

        # chart
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for name in [f'Top {n}' for n in (1, 2, n_list[-1])]:
            path = wealth_path(net_returns[name].reindex(months))
            ax.plot(path.index, path.values, label=name)
        path = wealth_path(bet)
        ax.plot(path.index, path.values, label='BET-TR', color='black', linestyle='--')
        log_axis_in_multiples(ax)
        ax.set_ylabel('Value of 1 leu invested (log scale)')
        ax.set_title(f'How many winners to hold? {len(stocks)} stocks, after costs')
        ax.legend()
        fig.tight_layout()
        save_fig(fig, f'concentration_chart_{label}.png')
        plt.close(fig)

        sheets[f'{label}_summary'] = table
        sheets[f'{label}_yearly'] = yearly.reset_index().rename(columns={'index': 'year'})
        held = pd.DataFrame({name: h.reindex(months) for name, h in holdings.items()})
        sheets[f'{label}_holdings'] = held.reset_index().rename(columns={'index': 'month'})

    with pd.ExcelWriter('concentration.xlsx') as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    print('\nSaved concentration.xlsx and the charts')
