"""
charts_1000_lei.py - how would 1,000 lei have grown? (paper Figures 2, 3 and A1)

Four charts, each with a log scale and a normal scale:
  chart_1_fixed13      - 13 fixed stocks: Top 1/2/3, winners, all stocks, losers, BET-TR
  chart_2_rulebased15  - the same in the rule-based universe
  chart_3_walkforward  - walk-forward strategies (2018-2025) vs BET-TR
  chart_4_index_timing - holding BET-TR vs timing it (cash earns the BNR rate)
Stock strategies are after a 0.5% trading cost.
Also saves values_1000_lei.xlsx with the month-by-month values.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

from common import (MAIN, K_MAIN, BASE_COST, load_pool, fixed_universe, rule_based_universe,
                    rf_for_holding_month, save_fig, wealth_path)
from portfolios import portfolio, top_n
from walk_forward import grid_returns, walk_forward, ROLLING_YEARS

START = 1000    # lei
# one distinct colour per line, so no two lines can be confused
STYLE = {'Top 1': dict(color='#1f77b4'),
         'Top 2': dict(color='#ff7f0e'),
         'Top 3': dict(color='#2ca02c'),
         'Winners top 30%': dict(color='#9467bd'),
         'Equal-weight all stocks': dict(color='grey'),
         'BET-TR': dict(color='black', linewidth=2.2, linestyle='--'),
         'Losers bottom 30%': dict(color='firebrick', linestyle=':', linewidth=2)}
MIN_LABEL_GAP = 0.06    # minimum vertical distance between end labels (log10 units, about 15%)


def spread_labels(end_values, log_scale):
    """Positions for the end-value labels, moved apart so that no two labels overlap."""
    order = sorted(end_values, key=end_values.get)
    to_axis = (lambda v: np.log10(v)) if log_scale else (lambda v: v)
    from_axis = (lambda y: 10 ** y) if log_scale else (lambda y: y)
    gap = MIN_LABEL_GAP if log_scale else (max(end_values.values()) - min(end_values.values())) * 0.04
    positions, previous = {}, None
    for name in order:
        y = to_axis(end_values[name])
        if previous is not None and y < previous + gap:
            y = previous + gap
        positions[name] = from_axis(y)
        previous = y
    return positions


def lei(value):
    """12345.6 -> '12.346 lei' (Romanian thousands separator)."""
    return f'{value:,.0f}'.replace(',', '.') + ' lei'


def stock_strategies(stocks, index_m):
    """Net monthly returns of every long-only strategy, all on the same months."""
    winners = portfolio(stocks, MAIN, 'winners')
    everyone = portfolio(stocks, MAIN, 'all')
    losers = portfolio(stocks, MAIN, 'losers')
    months = winners.returns.index

    def net(p):
        return (p.returns - BASE_COST * p.turnover).reindex(months)

    lines = {}
    for n in [1, 2, 3]:
        lines[f'Top {n}'] = net(top_n(stocks, MAIN, n))
    lines['Winners top 30%'] = net(winners)
    lines['Equal-weight all stocks'] = net(everyone)
    lines['BET-TR'] = index_m['next_1m'].reindex(months)
    lines['Losers bottom 30%'] = net(losers)
    return lines


def draw(lines, title, filename):
    """Draw the growth of 1,000 lei for every line, once on a log and once on a normal scale."""
    paths = {name: wealth_path(r, start=START) for name, r in lines.items()}
    for log_scale in [True, False]:
        fig, ax = plt.subplots(figsize=(10, 5.5))
        label_y = spread_labels({name: path.iloc[-1] for name, path in paths.items()}, log_scale)
        for name, path in paths.items():
            ax.plot(path.index, path.values, label=name, **STYLE.get(name, {}))
            # end value written to the right of the line, moved up if it would overlap another
            ax.annotate(lei(path.iloc[-1]), xy=(path.index[-1], path.iloc[-1]),
                        xytext=(path.index[-1] + pd.Timedelta(days=45), label_y[name]), textcoords='data',
                        va='center', fontsize=8, color=STYLE.get(name, {}).get('color', 'black'))
        if log_scale:
            ax.set_yscale('log')
            ax.yaxis.set_major_locator(FixedLocator([500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]))
            ax.yaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: lei(value)))
        ax.axhline(START, color='grey', linewidth=0.8)
        ax.grid(True, axis='y', alpha=0.3)
        ax.margins(x=0.12)                          # room for the end-value labels
        ax.set_title(title + (', log scale' if log_scale else ''))
        ax.set_ylabel('Value of the investment')
        ax.legend(loc='upper left', fontsize=9)
        fig.tight_layout()
        save_fig(fig, f"{filename}_{'log' if log_scale else 'linear'}.png")
        plt.close(fig)
    return paths


if __name__ == '__main__':
    index_m, pool = load_pool()
    fixed = fixed_universe(pool)
    rule_based = rule_based_universe(pool)
    all_paths = {}

    # charts 1-2: stock strategies, 2016-2025
    for stocks, name, file in [(fixed, '13 fixed stocks', 'chart_1_fixed13'),
                               (rule_based, f'rule-based universe, {K_MAIN} most liquid stocks', 'chart_2_rulebased15')]:
        paths = draw(stock_strategies(stocks, index_m),
                     f'1,000 lei invested, {name} (after {BASE_COST:.1%} cost)', file)
        all_paths.update({f'{file}: {k}': v for k, v in paths.items()})

    # chart 3: walk-forward, 2018-2025
    wf_lines = {}
    for stocks, name in [(fixed, 'fixed 13'), (rule_based, f'rule-based {K_MAIN}')]:
        months = portfolio(stocks, MAIN, 'winners').returns.index
        candidates = grid_returns(stocks, months)
        rf = rf_for_holding_month(months)
        expanding, _ = walk_forward(candidates, rf)
        rolling, _ = walk_forward(candidates, rf, window=ROLLING_YEARS)
        wf_lines[f'Walk-forward expanding, {name}'] = expanding
        wf_lines[f'Walk-forward rolling {ROLLING_YEARS}y, {name}'] = rolling
    oos = wf_lines['Walk-forward expanding, fixed 13'].index
    wf_lines['BET-TR'] = index_m['next_1m'].reindex(oos)
    paths = draw({k: v.reindex(oos) for k, v in wf_lines.items()},
                 f'1,000 lei invested in 2018, walk-forward strategies (after {BASE_COST:.1%} cost)',
                 'chart_3_walkforward')
    all_paths.update({f'chart_3: {k}': v for k, v in paths.items()})

    # chart 4: timing the index with its 12-month return; cash earns the BNR rate
    data = index_m.dropna(subset=['trail_12m', 'next_1m'])
    rf = rf_for_holding_month(data.index)
    went_up = (data['trail_12m'] > 0).astype(float)
    paths = draw({'BET-TR, always invested': data['next_1m'],
                  'Momentum: hold BET-TR only after an up year': went_up * data['next_1m'] + (1 - went_up) * rf,
                  'Reversal: hold BET-TR only after a down year': (1 - went_up) * data['next_1m'] + went_up * rf,
                  'Cash at BNR rate': rf},
                 '1,000 lei: holding vs timing the BET-TR index', 'chart_4_index_timing')
    all_paths.update({f'chart_4: {k}': v for k, v in paths.items()})

    # summary and Excel
    final = pd.Series({k: v.iloc[-1] for k, v in all_paths.items()}).round(0)
    print('\nFinal value of 1,000 lei:')
    print(final.to_string())
    with pd.ExcelWriter('values_1000_lei.xlsx') as xw:
        final.rename('final value (lei)').to_frame().to_excel(xw, sheet_name='final_values')
        for chart in ['chart_1', 'chart_2', 'chart_3', 'chart_4']:
            columns = {k.split(': ', 1)[1]: v for k, v in all_paths.items() if k.startswith(chart)}
            pd.DataFrame(columns).round(0).to_excel(xw, sheet_name=f'{chart}_monthly')
    print('\nSaved 8 charts (chart_*_log.png / chart_*_linear.png) and values_1000_lei.xlsx')
