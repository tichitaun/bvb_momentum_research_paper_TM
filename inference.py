"""
inference.py - how sensitive are the main results to the statistical method? (paper Table D1)

For each key monthly series:
  A) Newey-West t-statistics with lag lengths 0 (plain), 1, 3, 6 and 12
  B) 95% confidence intervals: Newey-West, and a circular block bootstrap (blocks of
     6 months, 10,000 resamples, fixed seed) that keeps the short-run dependence
  C) the estimate after removing the 1, 3 and 5 best months (a sensitivity check)
  D) monthly and annual mean, share of positive months

Saves inference.xlsx.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import MAIN, K_MAIN, BASE_COST, load_pool, fixed_universe, rule_based_universe
from portfolios import wml_series, leg_returns, avoid_losers

SEED, BLOCK, N_BOOT = 42, 6, 10000


def newey_west(x, lags):
    """Mean, standard error, t and p of a series (lags=0 means ordinary standard errors)."""
    ones = np.ones(len(x))
    if lags > 0:
        fit = sm.OLS(x.values, ones).fit(cov_type='HAC', cov_kwds={'maxlags': lags})
    else:
        fit = sm.OLS(x.values, ones).fit()
    return fit.params[0], fit.bse[0], fit.tvalues[0], fit.pvalues[0]


def block_bootstrap(x, rng):
    """Resample blocks of 6 consecutive months (wrapping around at the end) 10,000 times.

    Returns the 2.5% and 97.5% percentiles of the resampled means, and the share of
    resampled means that are zero or below.
    """
    values, n = x.values, len(x)
    n_blocks = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n, size=(N_BOOT, n_blocks))
    # each block = start, start+1, ..., start+5 ; then cut to n months, wrap with % n
    positions = starts[:, :, None] + np.arange(BLOCK)[None, None, :]
    positions = positions.reshape(N_BOOT, -1)[:, :n] % n
    means = values[positions].mean(axis=1)
    return np.percentile(means, [2.5, 97.5]), (means <= 0).mean()


def analyse(name, role, x, rng):
    x = pd.Series(x).dropna().astype(float)
    row = dict(series=name, role=role, months=len(x), monthly_mean=x.mean(),
               annualised=x.mean() * 12, pct_positive=(x > 0).mean())

    for lags in [0, 1, 3, 6, 12]:
        _, _, t, p = newey_west(x, lags)
        row[f't_lag{lags}'] = t
        row[f'p_lag{lags}'] = p

    mean, se, _, _ = newey_west(x, 3)
    row['CI95_NW_low'] = (mean - 1.96 * se) * 12
    row['CI95_NW_high'] = (mean + 1.96 * se) * 12

    (low, high), share_not_positive = block_bootstrap(x, rng)
    row['CI95_boot_low'], row['CI95_boot_high'] = low * 12, high * 12
    row['p_boot_one_sided'] = share_not_positive

    best_first = x.sort_values(ascending=False)
    for k in [1, 3, 5]:
        without_best = x.drop(best_first.index[:k])
        _, _, t, _ = newey_west(without_best, 3)
        row[f'annualised_without_best_{k}'] = without_best.mean() * 12
        row[f't_without_best_{k}'] = t
    return row


if __name__ == '__main__':
    pd.set_option('display.width', 250)
    rng = np.random.default_rng(SEED)

    index_m, pool = load_pool()
    fixed = fixed_universe(pool)
    rule_based = rule_based_universe(pool)

    legs_fixed, legs_rule = leg_returns(fixed, MAIN), leg_returns(rule_based, MAIN)
    avoid = avoid_losers(fixed, MAIN, 'frac')
    everyone = avoid_losers(fixed, MAIN, 0)
    avoid_minus_all = (avoid.returns - BASE_COST * avoid.turnover) - (everyone.returns - BASE_COST * everyone.turnover)

    rows = [analyse('Winners - losers, fixed 13', 'primary', wml_series(fixed, MAIN), rng),
            analyse(f'Winners - losers, rule-based {K_MAIN}', 'robustness', wml_series(rule_based, MAIN), rng),
            analyse('All stocks - losers, fixed 13', 'follow-up', legs_fixed['all'] - legs_fixed['losers'], rng),
            analyse(f'All stocks - losers, rule-based {K_MAIN}', 'follow-up', legs_rule['all'] - legs_rule['losers'], rng),
            analyse('Avoid-losers - equal-weight, fixed 13, after 0.5% cost', 'follow-up', avoid_minus_all, rng)]
    out = pd.DataFrame(rows)

    show = ['series', 'months', 'annualised', 'pct_positive', 't_lag0', 't_lag1', 't_lag3', 't_lag6',
            't_lag12', 'CI95_NW_low', 'CI95_NW_high', 'CI95_boot_low', 'CI95_boot_high',
            'annualised_without_best_1', 'annualised_without_best_3', 'annualised_without_best_5',
            't_without_best_5']
    print(out[show].round(3).to_string(index=False))
    out.to_excel('inference.xlsx', index=False)
    print('\nSaved inference.xlsx')
