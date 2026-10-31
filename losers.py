"""
losers.py - is "avoid the losers" the robust part of momentum? (paper Table 8, Figures 4-5)

A) Which side drives momentum? Winners minus losers is split into
       (winners - all stocks)  +  (all stocks - losers)
   where "all stocks" is the equal-weighted portfolio of the same stocks, same months.
B) "Avoid losers" portfolios: hold every stock EXCEPT the worst ones, equal weights, after
   costs. Compared with BET-TR and with all stocks (alpha_vs_EW = value of excluding losers).
C) How reliable is it? By sub-period and by calendar year.

Saves losers.xlsx and losers_chart.png.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import statsmodels.api as sm
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

from common import (CORE, SIGNALS, MAIN, K_MAIN, BASE_COST, load_pool, fixed_universe,
                    rule_based_universe, rf_for_holding_month, evaluate, mean_test, stars,
                    calendar_year_returns, print_table, save_fig, wealth_path)
from portfolios import leg_returns, avoid_losers


def test_row(x, label, **extra):
    """Mean of a monthly series with its Newey-West t-statistic, as a table row."""
    x = x.dropna()
    mean, t, p = mean_test(x)
    return dict(test=label, **extra, annualized=mean * 12, t_NW=t, p=p, sig=stars(p),
                months=len(x), pct_positive=(x > 0).mean())


def alpha_against(r, benchmark, rf):
    """Alpha of r against any benchmark, both in excess of the risk-free rate."""
    data = pd.DataFrame({'y': r - rf, 'x': benchmark - rf}).dropna()
    fit = sm.OLS(data['y'], sm.add_constant(data['x'])).fit(cov_type='HAC', cov_kwds={'maxlags': 3})
    return fit.params['const'] * 12, fit.tvalues['const'], fit.pvalues['const']


if __name__ == '__main__':
    pd.set_option('display.width', 230)
    pd.set_option('display.max_rows', 300)

    index_m, pool = load_pool()
    universes = {'Core 7': {t: pool[t] for t in CORE if t in pool},
                 'Fixed 13': fixed_universe(pool),
                 f'Rule-based {K_MAIN}': rule_based_universe(pool)}

    # ---------------------------------------------------------------- A) which side?
    A = []
    for universe, stocks in universes.items():
        for signal in SIGNALS:
            legs = leg_returns(stocks, signal)
            A.append(test_row(legs['winners'] - legs['all'], 'winners - all', universe=universe, signal=signal))
            A.append(test_row(legs['all'] - legs['losers'], 'all - losers', universe=universe, signal=signal))
        legs = leg_returns(stocks, MAIN, sector_neutral=True)
        A.append(test_row(legs['winners'] - legs['all'], 'winners - all, sector-neutral', universe=universe, signal=MAIN))
        A.append(test_row(legs['all'] - legs['losers'], 'all - losers, sector-neutral', universe=universe, signal=MAIN))
    A = pd.DataFrame(A)
    print_table('A) Which leg drives momentum? (annualised, gross of costs)', A)

    # ---------------------------------------------------------------- B) avoid-losers portfolios
    B, paths = [], {}
    for universe, stocks in universes.items():
        everyone = avoid_losers(stocks, MAIN, n_drop=0)          # dropping 0 stocks = all stocks
        months = everyone.returns.index
        bet = index_m['next_1m'].reindex(months)
        rf = rf_for_holding_month(months)
        everyone_net = everyone.returns - BASE_COST * everyone.turnover

        variants = [(0, 'Equal-weight all (benchmark)'), (1, 'Exclude worst 1'),
                    (2, 'Exclude worst 2'), ('frac', 'Exclude bottom 30%')]
        for n_drop, name in variants:
            signals_to_test = [MAIN] if n_drop == 0 else SIGNALS
            for signal in signals_to_test:
                p = avoid_losers(stocks, signal, n_drop)
                net = (p.returns - BASE_COST * p.turnover).reindex(months)
                row = evaluate(net, bet, rf, f'{universe} | {name} | {signal}', p.turnover)
                alpha, t, p_value = alpha_against(net, everyone_net, rf)
                row.update(alpha_vs_EW=alpha, t_vs_EW=t, p_vs_EW=p_value, sig_vs_EW=stars(p_value))
                B.append(row)
                if signal == MAIN:
                    paths[(universe, name)] = net
        B.append(evaluate(bet, bet, rf, f'{universe} | BET-TR'))
        paths[(universe, 'BET-TR')] = bet
    B = pd.DataFrame(B)
    print_table(f'B) Avoid-losers portfolios, after {BASE_COST:.1%} cost', B, 3)

    # ---------------------------------------------------------------- C) reliability
    C, Y = [], []
    for universe, stocks in universes.items():
        legs = leg_returns(stocks, MAIN)
        loser_gap = legs['all'] - legs['losers']           # how much losers lag the average

        crisis = (loser_gap.index >= pd.Period('2021-01', 'M')) & (loser_gap.index <= pd.Period('2022-12', 'M'))
        parts = [('formed 2016-2019', loser_gap[:'2019-12']),
                 ('formed 2020-2025', loser_gap['2020-01':]),
                 ('formed excl. 2021-2022', loser_gap[~crisis])]
        for label, part in parts:
            C.append(test_row(part, f'all - losers, {label}', universe=universe, signal=MAIN))

        yearly = calendar_year_returns(legs[['losers', 'all']].astype(float))
        yearly['losers_lagged'] = yearly['losers'] < yearly['all']
        yearly.insert(0, 'universe', universe)
        Y.append(yearly.reset_index(names='year'))
    C = pd.DataFrame(C)
    Y = pd.concat(Y, ignore_index=True)
    print_table('C) Loser effect by sub-period (all stocks minus losers, 12-1)', C)
    print_table('C2) Calendar years: did the losers lag the equal-weighted portfolio?', Y, 3)
    for universe in universes:
        years = Y[Y['universe'] == universe]
        print(f"{universe}: losers lagged in {years['losers_lagged'].sum()} of {len(years)} years")

    # ---------------------------------------------------------------- Figure 4
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for name, style in [('Exclude bottom 30%', '-'), ('Equal-weight all (benchmark)', '--'), ('BET-TR', ':')]:
        path = wealth_path(paths[('Fixed 13', name)], start=1000)
        ax.plot(path.index, path.values, linestyle=style, label=name.replace(' (benchmark)', ''))
    ax.set_yscale('log')
    ax.yaxis.set_major_locator(FixedLocator([1000, 2000, 5000, 10000, 20000]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:,.0f}'.replace(',', '.') + ' lei'))
    ax.grid(True, axis='y', alpha=0.3)
    ax.set_title(f'Avoiding past losers, fixed 13-stock universe (after {BASE_COST:.1%} cost, log scale)')
    ax.legend()
    fig.tight_layout()
    save_fig(fig, 'losers_chart.png')
    plt.close(fig)

    with pd.ExcelWriter('losers.xlsx') as xw:
        A.to_excel(xw, sheet_name='A_legs', index=False)
        B.to_excel(xw, sheet_name='B_avoid_losers', index=False)
        C.to_excel(xw, sheet_name='C_subperiods', index=False)
        Y.to_excel(xw, sheet_name='C2_yearly', index=False)
    print('\nSaved losers.xlsx and losers_chart.png')
