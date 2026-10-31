"""
robustness.py - is the winners-minus-losers result robust? (paper Table 4, Figure 1)

For the core 7 and the fixed 13 stocks, with the main 12-1 signal:
  A) sector-neutral version (is it just one sector beating another?)
  B) leave one stock out    (is it just one company?)
  C) sub-periods            (is it just one period?)
  D) alpha against BET-TR   (is it just exposure to the market?)

Saves robustness_core.xlsx, robustness_extended.xlsx and wml_chart_core/extended.png.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import statsmodels.api as sm

from common import (UNIVERSES, SIGNALS, MAIN, load_all, rf_for_holding_month,
                    summarize, print_table, save_fig, wealth_path)
from portfolios import wml_series


def subperiods(wml):
    """Split by FORMATION month (portfolios formed in ...); returns are earned a month later."""
    before_2020 = wml[:'2019-12']
    from_2020 = wml['2020-01':]
    crisis = (wml.index >= pd.Period('2021-01', 'M')) & (wml.index <= pd.Period('2022-12', 'M'))
    return {'formed 2016-2019': before_2020,
            'formed 2020-2025': from_2020,
            'formed excl. 2021-2022': wml[~crisis]}


def market_alpha(wml, index_m):
    """Regress WML on the market's excess return: WML = alpha + beta * (BET-TR - rf)."""
    market = index_m['next_1m'].reindex(wml.index)
    rf = rf_for_holding_month(wml.index)
    data = pd.DataFrame({'wml': wml, 'mkt_excess': market - rf}).dropna()
    fit = sm.OLS(data['wml'], sm.add_constant(data['mkt_excess'])).fit(
        cov_type='HAC', cov_kwds={'maxlags': 3})
    return pd.DataFrame([dict(alpha_monthly=fit.params['const'],
                              alpha_annual=fit.params['const'] * 12,
                              t_alpha=fit.tvalues['const'],
                              p_alpha=fit.pvalues['const'],
                              market_beta=fit.params['mkt_excess'],
                              t_beta=fit.tvalues['mkt_excess'],
                              months=len(data))])


if __name__ == '__main__':
    pd.set_option('display.width', 200)
    index_m, all_stocks = load_all()

    for label, tickers in UNIVERSES.items():
        stocks = {t: all_stocks[t] for t in tickers if t in all_stocks}
        print(f'\n\n################ {label.upper()} UNIVERSE: {len(stocks)} stocks ################')

        wml = wml_series(stocks, MAIN)
        wml_neutral = wml_series(stocks, MAIN, sector_neutral=True)

        # A) raw and sector-neutral, every signal
        rows = [summarize(wml_series(stocks, s), f'{s} raw') for s in SIGNALS]
        rows += [summarize(wml_series(stocks, s, sector_neutral=True), f'{s} sector-neutral')
                 for s in SIGNALS]
        A = pd.DataFrame(rows)
        print_table('A) Raw vs sector-neutral', A)

        # B) leave one stock out
        B = pd.DataFrame([summarize(wml_series(stocks, MAIN, drop=t), f'without {t}') for t in stocks])
        print_table(f'B) Leave-one-stock-out ({MAIN})', B)

        # C) sub-periods
        C = pd.DataFrame([summarize(part, name) for name, part in subperiods(wml).items()])
        print_table(f'C) Sub-periods ({MAIN})', C)

        # D) market-adjusted alpha
        D = market_alpha(wml, index_m)
        print_table(f'D) Market-adjusted alpha ({MAIN})', D)

        # Figure 1: growth of 1 leu in the zero-cost WML portfolio
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for series, name, style in [(wml, 'Winners minus losers (12-1)', '-'),
                                    (wml_neutral, 'Sector-neutral version', '--')]:
            path = wealth_path(series)
            ax.plot(path.index, path.values, label=name, linestyle=style)
        ax.axhline(1, color='grey', linewidth=0.8)
        ax.set_ylabel('Growth of 1 leu')
        ax.set_title(f'Cross-sectional momentum on the BVB, {len(stocks)} stocks')
        ax.legend()
        fig.tight_layout()
        save_fig(fig, f'wml_chart_{label}.png')
        plt.close(fig)

        with pd.ExcelWriter(f'robustness_{label}.xlsx') as xw:
            A.to_excel(xw, sheet_name='A_sector_neutral', index=False)
            B.to_excel(xw, sheet_name='B_leave_one_out', index=False)
            C.to_excel(xw, sheet_name='C_subperiods', index=False)
            D.to_excel(xw, sheet_name='D_market_alpha', index=False)
        print(f'\nSaved robustness_{label}.xlsx and wml_chart_{label}.png')
