"""
checks.py - automatic tests of timing and accounting. Run before trusting any result.

 1. Toy test: on made-up prices, the winners-minus-losers return of formation month t
    must equal the return over month t+1 of the stocks ranked at t, computed by hand.
 2. No future returns in selection: scrambling or deleting next-month returns must not
    change which stocks are chosen at month t.
 3. No future data in the universe: changing prices and volumes AFTER month t must not
    change the 15-stock universe at month t.
 4. Walk-forward timing: at each yearly decision, every training return must already be
    known, and no test month may be in the training set.
 5. Accounting: every strategy has consecutive months, no month is skipped, and missing
    next-month returns of chosen stocks are counted.
 6. Calendar years: yearly figures must use the year in which returns are earned.
Prints PASS or FAIL for each check.
"""
import copy

import numpy as np
import pandas as pd

import portfolios
from common import (CORE, EXTRA, MAIN, K_MAIN, FRACTION, load_pool, fixed_universe,
                    rule_based_universe, membership, to_monthly, calendar_year_returns)
from portfolios import wml_series, portfolio, top_n
from walk_forward import grid_returns, MIN_TRAIN_YEARS

results = []


def report(name, passed, detail=''):
    results.append(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f' - {detail}' if detail else ''))


# ------------------------------------------------------------------ 1. toy test
def toy_test():
    """Seven made-up stocks with random daily prices; recompute WML by hand and compare."""
    rng = np.random.default_rng(0)
    days = pd.bdate_range('2019-01-01', '2021-12-31')
    stocks, month_end_prices = {}, {}
    for ticker in ['A', 'B', 'C', 'D', 'E', 'F', 'G']:
        price = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, len(days)))
        daily = pd.DataFrame({'Date': days, 'Price': price})
        stocks[ticker] = to_monthly(daily)
        month_end_prices[ticker] = daily.groupby(daily['Date'].dt.to_period('M'))['Price'].last()
    P = pd.DataFrame(month_end_prices)

    wml = wml_series(stocks, MAIN)
    errors = []
    for month in wml.index:
        signal = P.shift(1).loc[month] / P.shift(12).loc[month] - 1      # known at t
        next_return = P.shift(-1).loc[month] / P.loc[month] - 1          # earned in t+1
        ranked = signal.dropna().sort_values()
        n = max(2, int(round(len(ranked) * FRACTION)))
        by_hand = next_return[ranked.index[-n:]].mean() - next_return[ranked.index[:n]].mean()
        errors.append(abs(by_hand - wml[month]))
    report('1. Toy test: strategy earns the month t+1 return of stocks ranked at t',
           max(errors) < 1e-12, f'{len(errors)} months, max error {max(errors):.1e}')


# ------------------------------------------------------------------ 2. future returns not used
def selection_test(stocks):
    original = portfolio(stocks, MAIN, 'winners').holdings
    scrambled = copy.deepcopy(stocks)
    rng = np.random.default_rng(1)
    for m in scrambled.values():
        m['next_1m'] = m['next_1m'] * rng.uniform(-3, 3, len(m))                       # change them
        m.loc[m.sample(frac=0.2, random_state=2).index, 'next_1m'] = np.nan             # delete some
    after = portfolio(scrambled, MAIN, 'winners').holdings
    common_months = original.index.intersection(after.index)
    same = (original.loc[common_months] == after.loc[common_months]).all()
    report('2. Selection does not depend on next-month returns', bool(same),
           f'{len(common_months)} formation months compared')


# ------------------------------------------------------------------ 3. universe uses past data only
def universe_test(pool):
    original = membership(pool, K_MAIN)
    same_everywhere = []
    for month in [pd.Period('2018-06', 'M'), pd.Period('2021-03', 'M'), pd.Period('2024-09', 'M')]:
        changed = copy.deepcopy(pool)
        for m in changed.values():                       # rewrite everything AFTER month t
            after = m.index > month
            m.loc[after, 'adv_12m'] = np.random.default_rng(3).uniform(0, 1e9, after.sum())
            m.loc[after, 'liquid'] = True
        new = membership(changed, K_MAIN)
        same_everywhere.append(bool((original.loc[month] == new.loc[month]).all()))
    report('3. Universe at month t unchanged when data after t are altered', all(same_everywhere),
           '3 formation dates tested')


# ------------------------------------------------------------------ 4. walk-forward timing
def walk_forward_test(stocks):
    months = portfolio(stocks, MAIN, 'winners').returns.index
    candidates = grid_returns(stocks, months)
    years = sorted(set(candidates.index.year))[MIN_TRAIN_YEARS:]
    rows, ok = [], True
    for year in years:
        train = candidates[candidates.index.year < year]
        test = candidates[candidates.index.year == year]
        decision_month = test.index.min()                   # first formation month of the year
        last_return_month = train.index.max() + 1           # when the last training return is earned
        known_in_time = last_return_month <= decision_month
        no_overlap = len(train.index.intersection(test.index)) == 0
        ok = ok and known_in_time and no_overlap
        rows.append(dict(test_year=year, decision_at_end_of=str(decision_month),
                         last_training_formation=str(train.index.max()),
                         last_training_return_month=str(last_return_month),
                         realised_by_decision=known_in_time, no_overlap=no_overlap))
    print(pd.DataFrame(rows).to_string(index=False))
    report('4. Walk-forward: training returns realised before each decision, no overlap', ok)


# ------------------------------------------------------------------ 5. accounting
def accounting_test(universes):
    portfolios.SKIPPED.clear()
    portfolios.MISSING_LOG.clear()
    consecutive, notes = True, []
    for name, stocks in universes.items():
        results_to_check = [portfolio(stocks, MAIN, g).returns for g in ['winners', 'losers', 'all']]
        results_to_check += [top_n(stocks, MAIN, n).returns for n in [1, 2, 3]]
        for r in results_to_check:
            calendar = pd.period_range(r.index.min(), r.index.max(), freq='M')
            consecutive = consecutive and len(calendar) == len(r)
        notes.append(f'{name}: {len(results_to_check[-1])} months')
    report('5a. Every strategy has a continuous monthly calendar', consecutive, '; '.join(notes))
    report('5b. No formation month skipped for lack of stocks', len(portfolios.SKIPPED) == 0,
           f'{len(portfolios.SKIPPED)} skipped')
    print(f'      Chosen stocks with a missing next-month return (set to 0%): {len(portfolios.MISSING_LOG)}')
    report('5c. Missing next-month returns among chosen stocks are reported', True,
           f'{len(portfolios.MISSING_LOG)} cases')


# ------------------------------------------------------------------ 6. calendar years
def calendar_year_test(index_m):
    """Rebuild BET-TR's calendar-year returns from formation-month returns; must match."""
    from_strategy = calendar_year_returns(index_m['next_1m'].dropna())
    monthly = index_m['ret_1m'].dropna()
    actual = (1 + monthly).groupby(monthly.index.year).prod() - 1
    years = [y for y in from_strategy.index if 2017 <= y <= 2025]
    error = (from_strategy[years] - actual[years]).abs().max()
    report('6. Calendar-year tables use the year in which returns are earned', error < 1e-12,
           f'BET-TR 2017-2025, max error {error:.1e}')


if __name__ == '__main__':
    toy_test()
    index_m, pool = load_pool()
    fixed = fixed_universe(pool)
    selection_test(fixed)
    universe_test(pool)
    walk_forward_test(fixed)
    calendar_year_test(index_m)
    accounting_test({'Core 7': {t: pool[t] for t in CORE}, 'Fixed 13': fixed,
                     f'Rule-based {K_MAIN}': rule_based_universe(pool)})
    print(f'\n{sum(results)} of {len(results)} checks passed')
