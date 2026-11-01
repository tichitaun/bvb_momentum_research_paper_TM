"""
sensitivity.py - do the hand-made data corrections change the main results? (referee point A6)

Four versions of the data:
  1. Baseline                - the verified dividend corrections and the one-day spike rule
  2. No corrections          - Yahoo's adjusted prices exactly as downloaded (no corrections,
                               no spike rule)
  3. Without BNET and ROCE   - drop the two stocks whose corrections are least certain
                               (Bittnet's 2021 bonus issue could not be rebuilt; Romcarbon's
                               dividend was halved for a later bonus issue)
  4. Without TTS             - drop the stock with the one-day price spike

For each version, in the fixed 13 and the rule-based 15 universes (12-1 signal):
  - winners minus losers
  - all stocks minus losers (the loser effect)
  - avoid-losers minus equal-weight: alpha after a 0.5% trading cost
Saves sensitivity.xlsx.
"""
import pandas as pd

import common
from common import MAIN, BASE_COST, fixed_universe, rule_based_universe, rf_for_holding_month, mean_test, stars
from portfolios import wml_series, leg_returns, avoid_losers
from losers import alpha_against

VERSIONS = {
    'Baseline (verified corrections)': dict(no_corrections=False, drop=[]),
    'No corrections (Yahoo data as downloaded)': dict(no_corrections=True, drop=[]),
    'Without BNET and ROCE': dict(no_corrections=False, drop=['BNET', 'ROCE']),
    'Without TTS': dict(no_corrections=False, drop=['TTS']),
}


def load(no_corrections, drop):
    """Load the pool, optionally switching off the corrections and the spike rule."""
    saved_corrections, saved_spikes = dict(common.CORRECTIONS), common.find_spikes
    if no_corrections:
        common.CORRECTIONS.clear()
        common.find_spikes = lambda returns: []
    try:
        index_m, pool = common.load_pool()
    finally:
        common.CORRECTIONS.update(saved_corrections)
        common.find_spikes = saved_spikes
    return index_m, {t: m for t, m in pool.items() if t not in drop}


def row(version, universe, test, annual, t, p):
    return dict(version=version, universe=universe, test=test, annualized=annual, t_NW=t, p=p, sig=stars(p))


if __name__ == '__main__':
    pd.set_option('display.width', 200)
    rows = []
    for version, settings in VERSIONS.items():
        print(f'\n--- {version} ---')
        index_m, pool = load(**settings)
        for universe, stocks in [('Fixed 13', fixed_universe(pool)), ('Rule-based 15', rule_based_universe(pool))]:
            wml = wml_series(stocks, MAIN)
            mean, t, p = mean_test(wml)
            rows.append(row(version, universe, 'winners - losers', mean * 12, t, p))

            legs = leg_returns(stocks, MAIN)
            mean, t, p = mean_test(legs['all'] - legs['losers'])
            rows.append(row(version, universe, 'all stocks - losers', mean * 12, t, p))

            avoid = avoid_losers(stocks, MAIN, 'frac')
            everyone = avoid_losers(stocks, MAIN, 0)
            months = everyone.returns.index
            rf = rf_for_holding_month(months)
            alpha, t, p = alpha_against((avoid.returns - BASE_COST * avoid.turnover).reindex(months),
                                        everyone.returns - BASE_COST * everyone.turnover, rf)
            rows.append(row(version, universe, 'avoid-losers alpha vs equal-weight (after 0.5% cost)', alpha, t, p))

    table = pd.DataFrame(rows)
    print('\n=== Sensitivity of the main results to the data corrections (12-1 signal, arithmetic annualised) ===')
    print(table.round(4).to_string(index=False))
    table.to_excel('sensitivity.xlsx', index=False)
    print('\nSaved sensitivity.xlsx')
