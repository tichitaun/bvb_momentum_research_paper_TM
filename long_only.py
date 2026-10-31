"""
long_only.py - the realistic strategy without short selling (paper Table 5).

Each month: buy the top 30% of stocks by 12-1 return in equal amounts, hold for one
month, then sell the stocks that dropped out and buy the new winners. Compared with
BET-TR, with all stocks in equal amounts, and with the losers. A trading cost is charged
on every leu bought or sold.

Saves long_only.xlsx and long_only_chart_core/extended.png.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from common import (UNIVERSES, FRACTION, MAIN, BASE_COST, load_all, rf_for_holding_month,
                    evaluate, calendar_year_returns, print_table, save_fig, wealth_path,
                    log_axis_in_multiples)
from portfolios import portfolio

COSTS = [0.0, 0.0025, 0.005, 0.01, 0.02]   # cost per leu bought or sold (one-way)


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    index_m, all_stocks = load_all()
    sheets = {}

    for label, tickers in UNIVERSES.items():
        stocks = {t: all_stocks[t] for t in tickers if t in all_stocks}
        print(f'\n\n################ {label.upper()} UNIVERSE: {len(stocks)} stocks ################')

        winners = portfolio(stocks, MAIN, 'winners')
        losers = portfolio(stocks, MAIN, 'losers')
        everyone = portfolio(stocks, MAIN, 'all')

        months = winners.returns.index
        bet = index_m['next_1m'].reindex(months)                 # BET-TR in the same months
        rf = rf_for_holding_month(months)

        def after_costs(p, cost=BASE_COST):
            """Net return = gross return - cost x turnover."""
            return p.returns - cost * p.turnover

        # 1) winners at different trading costs
        rows = [evaluate(after_costs(winners, c), bet, rf, f'Winners, cost {c:.2%}', winners.turnover)
                for c in COSTS]
        rows.append(evaluate(bet, bet, rf, 'BET-TR (buy and hold)'))
        cost_table = pd.DataFrame(rows)
        print_table(f'1) Long-only winners ({MAIN}, top {FRACTION:.0%}) at different trading costs',
                    cost_table, 3)

        # break-even cost: the cost per leu at which winners would only match BET-TR on average
        break_even = (winners.returns - bet).mean() / winners.turnover.mean()
        print(f'\nBreak-even cost per leu traded: {break_even:.2%} '
              f'(average monthly turnover {winners.turnover.mean():.0%})')

        # 2) all portfolios at the baseline cost
        comparison = pd.DataFrame([
            evaluate(after_costs(winners), bet, rf, 'Winners (top 30%)', winners.turnover),
            evaluate(after_costs(everyone), bet, rf, 'Equal-weight all stocks', everyone.turnover),
            evaluate(after_costs(losers), bet, rf, 'Losers (bottom 30%)', losers.turnover),
            evaluate(bet, bet, rf, 'BET-TR (buy and hold)')])
        print_table(f'2) Comparison after {BASE_COST:.2%} trading cost', comparison, 3)

        # 3) calendar years (the year in which each return is earned)
        yearly = calendar_year_returns(pd.DataFrame({'Winners': after_costs(winners), 'BET-TR': bet}))
        yearly['Difference'] = yearly['Winners'] - yearly['BET-TR']
        print('\n=== 3) Calendar-year returns ===')
        print(yearly.round(3).to_string())

        # chart: growth of 1 leu
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for series, name, style in [(after_costs(winners), 'Winners (top 30%), after costs', '-'),
                                    (bet, 'BET-TR', '-'),
                                    (after_costs(everyone), 'Equal-weight all stocks', '--'),
                                    (after_costs(losers), 'Losers (bottom 30%)', ':')]:
            path = wealth_path(series)
            ax.plot(path.index, path.values, label=name, linestyle=style)
        log_axis_in_multiples(ax)
        ax.set_ylabel('Value of 1 leu invested (log scale)')
        ax.set_title(f'Long-only momentum vs BET-TR, {len(stocks)} stocks ({BASE_COST:.1%} cost per trade)')
        ax.legend()
        fig.tight_layout()
        save_fig(fig, f'long_only_chart_{label}.png')
        plt.close(fig)

        sheets[f'{label}_costs'] = cost_table
        sheets[f'{label}_comparison'] = comparison
        sheets[f'{label}_yearly'] = yearly.reset_index().rename(columns={'index': 'year'})
        sheets[f'{label}_holdings'] = winners.holdings.rename('winners held').reset_index()

    with pd.ExcelWriter('long_only.xlsx') as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
    print('\nSaved long_only.xlsx and the charts')
