"""
analysis.py - the main tests (paper Tables 2 and 3).

For the core 7 stocks and for the fixed 13 stocks (plus the BET-TR index):
  1) Predictive regressions : does an asset's own past return predict its next month?
  2) Timing strategies      : hold the asset only after an up (or down) period
  3) Pooled panel           : all stocks together, with stock fixed effects
  4) Winners minus losers   : top 30% minus bottom 30% by past return

Saves results_core.xlsx and results_extended.xlsx.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from common import (UNIVERSES, SIGNALS, FRACTION, load_all, rf_for_holding_month,
                    stars, summarize, annual_return, max_drawdown, sharpe_ratio, print_table)
from portfolios import wml_series


# =============================================================================
# 1) Predictive regressions:  next_1m = alpha + beta * signal + error
# =============================================================================

def newey_west_lags(signal):
    """Lag length = the look-back of the signal (12 for the 12-1 signal)."""
    if signal == 'trail_12_1m':
        return 12
    return int(signal.replace('trail_', '').replace('m', ''))     # 'trail_6m' -> 6


def predictive_regressions(m, asset):
    rows = []
    for signal in SIGNALS:
        data = m[[signal, 'next_1m']].dropna()
        X = sm.add_constant(data[signal])
        fit = sm.OLS(data['next_1m'], X).fit(cov_type='HAC',
                                              cov_kwds={'maxlags': newey_west_lags(signal)})
        p = fit.pvalues[signal]
        rows.append(dict(asset=asset, signal=signal, beta=fit.params[signal],
                         t_NW=fit.tvalues[signal], p=p, sig=stars(p), N=len(data)))
    return rows


# =============================================================================
# 2) Timing strategies on one asset (no trading costs)
# =============================================================================

def performance(r, rf, share_invested):
    return dict(ann_return=annual_return(r),
                ann_vol=r.std() * np.sqrt(12),
                sharpe=sharpe_ratio(r, rf),
                max_dd=max_drawdown(r),
                pct_in_market=share_invested,
                months=len(r))


def timing_strategies(m, asset):
    """Momentum: hold the asset in month t+1 only if its past return was positive.
    Reversal: hold it only if its past return was negative. Otherwise: cash at the BNR rate."""
    rows = []
    for signal in SIGNALS:
        data = m.dropna(subset=[signal, 'next_1m'])
        rf = rf_for_holding_month(data.index)
        went_up = (data[signal] > 0).astype(float)          # 1 after an up period, 0 otherwise

        buy_and_hold = data['next_1m']
        momentum = went_up * data['next_1m'] + (1 - went_up) * rf
        reversal = (1 - went_up) * data['next_1m'] + went_up * rf

        rows.append(dict(asset=asset, signal=signal, strategy='buy_and_hold',
                         **performance(buy_and_hold, rf, 1.0)))
        rows.append(dict(asset=asset, signal=signal, strategy='momentum',
                         **performance(momentum, rf, went_up.mean())))
        rows.append(dict(asset=asset, signal=signal, strategy='reversal',
                         **performance(reversal, rf, 1 - went_up.mean())))
    return rows


# =============================================================================
# 3) Pooled panel:  next_1m = a_stock + b * signal + error
# =============================================================================

def panel_regressions(stocks):
    """All stocks stacked. Each stock has its own intercept (fixed effect); standard errors
    are clustered by month because stocks move together in the same month."""
    panel = pd.concat([m.assign(ticker=t).reset_index() for t, m in stocks.items()],
                      ignore_index=True)
    rows = []
    for signal in SIGNALS:
        data = panel[['ticker', 'YearMonth', signal, 'next_1m']].dropna()
        data = data.rename(columns={signal: 'x'})
        month_id = pd.factorize(data['YearMonth'])[0]
        fit = smf.ols('next_1m ~ x + C(ticker)', data=data).fit(
            cov_type='cluster', cov_kwds={'groups': month_id})
        p = fit.pvalues['x']
        rows.append(dict(signal=signal, beta=fit.params['x'], t_clustered=fit.tvalues['x'],
                         p=p, sig=stars(p), N=len(data), stocks=data['ticker'].nunique()))
    return pd.DataFrame(rows)


# =============================================================================
# Run
# =============================================================================

if __name__ == '__main__':
    pd.set_option('display.width', 200)
    pd.set_option('display.max_rows', 500)

    index_m, all_stocks = load_all()

    print(f"{'asset':7s}{'first month':>12s}{'last month':>12s}{'months':>8s}{'illiquid':>10s}")
    print(f"{'BET-TR':7s}{str(index_m.index.min()):>12s}{str(index_m.index.max()):>12s}"
          f"{len(index_m):>8d}{'-':>10s}")
    for ticker, m in all_stocks.items():
        print(f"{ticker:7s}{str(m.index.min()):>12s}{str(m.index.max()):>12s}"
              f"{len(m):>8d}{(~m['liquid']).sum():>10d}")

    for label, tickers in UNIVERSES.items():
        stocks = {t: all_stocks[t] for t in tickers if t in all_stocks}
        assets = {'BET-TR': index_m, **stocks}
        print(f'\n\n################ {label.upper()} UNIVERSE: {len(stocks)} stocks ################')

        regressions = pd.DataFrame([row for name, m in assets.items()
                                    for row in predictive_regressions(m, name)])
        print_table('1) Predictive regressions: next_1m = a + b * signal (Newey-West t)', regressions)

        timing = pd.DataFrame([row for name, m in assets.items()
                               for row in timing_strategies(m, name)])
        print_table('2) Time-series strategies (long/flat, cash earns BNR rate)', timing, 3)

        panel = panel_regressions(stocks)
        print_table('3) Pooled panel: stock fixed effects, month-clustered SE', panel)

        wml = pd.DataFrame([summarize(wml_series(stocks, s), s) for s in SIGNALS])
        _, n_ranked = wml_series(stocks, 'trail_12_1m', return_sizes=True)
        print(f'\nstocks ranked per month: min {n_ranked.min()}, max {n_ranked.max()}, '
              f'average {n_ranked.mean():.1f}')
        print_table(f'4) Winners-minus-losers (top {FRACTION:.0%} - bottom {FRACTION:.0%})', wml)

        with pd.ExcelWriter(f'results_{label}.xlsx') as xw:
            regressions.to_excel(xw, sheet_name='1_regressions', index=False)
            timing.to_excel(xw, sheet_name='2_strategies', index=False)
            panel.to_excel(xw, sheet_name='3_panel', index=False)
            wml.to_excel(xw, sheet_name='4_cross_section', index=False)
        print(f'\nSaved results_{label}.xlsx')
