"""
loser_characteristics.py - what kind of stocks are the losers? (referee point A7)

Each month t, in the fixed 13 and rule-based 15 universes, stocks are ranked by the 12-1
signal into winners (top 30%), losers (bottom 30%) and all ranked stocks, exactly as in the
main tests. For every stock and month we measure, using only data up to the end of month t:

  amihud        Amihud illiquidity: average over the days of month t of
                |daily return| / lei traded that day, x 1,000,000 (higher = less liquid)
  adv_12m       average daily traded value over months t-11..t (lei)
  spread        estimated bid-ask spread (Abdi-Ranaldo), average of months t-2..t
  volatility    standard deviation of monthly returns over months t-11..t, x sqrt(12)
  beta          market beta against BET-TR over months t-23..t (at least 12 months)

Outputs (all descriptive; nothing here is a causal test):
  A) average characteristics of winners, losers and all stocks, and losers minus all with a
     Newey-West t-statistic
  B) how often each stock and each sector was in the loser group
  C) EXPLORATORY: the loser effect (all - losers) regressed on the market's excess return
     and on an illiquid-minus-liquid return spread (IML) built from the 32-stock pool
     (most illiquid third minus most liquid third by Amihud illiquidity, equal weights).
     With so few stocks, IML is a rough proxy, not a proper liquidity factor.
Saves loser_characteristics.xlsx.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import (MAIN, SECTORS, load_pool, load_stock, load_index, trading_days_per_month,
                    membership, restrict, fixed_universe, K_MAIN, rf_for_holding_month,
                    mean_test, stars)
from portfolios import number_per_side
from costs import monthly_spread_and_traded_value

CHARACTERISTICS = ['amihud', 'adv_12m', 'spread', 'volatility', 'beta']


def monthly_amihud(ticker):
    """Average of |daily total return| / lei traded, per month, x 1,000,000."""
    price = load_stock(ticker).set_index('Date')['Price']
    raw = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'], index_col='Date')
    raw = raw[raw['Volume'] > 0]
    value = (raw['Close'] * raw['Volume']).reindex(price.index)
    daily = (price.pct_change().abs() / value).replace([np.inf, -np.inf], np.nan) * 1e6
    return daily.groupby(daily.index.to_period('M')).mean()


def characteristics(pool, index_m, trading_days):
    """Months x stocks tables of every characteristic, each known at the end of month t."""
    market = index_m['ret_1m']
    tables = {name: {} for name in CHARACTERISTICS}
    for ticker, m in pool.items():
        r = m['ret_1m']
        tables['amihud'][ticker] = monthly_amihud(ticker).reindex(m.index)
        tables['adv_12m'][ticker] = m['adv_12m']
        spread, _ = monthly_spread_and_traded_value(ticker, trading_days)
        tables['spread'][ticker] = spread.rolling(3, min_periods=1).mean().reindex(m.index)
        tables['volatility'][ticker] = r.rolling(12, min_periods=12).std() * np.sqrt(12)
        both = pd.concat([r, market.reindex(r.index)], axis=1).dropna()
        cov = both.iloc[:, 0].rolling(24, min_periods=12).cov(both.iloc[:, 1])
        var = both.iloc[:, 1].rolling(24, min_periods=12).var()
        tables['beta'][ticker] = (cov / var).reindex(m.index)
    return {name: pd.DataFrame(values) for name, values in tables.items()}


def group_members(stocks):
    """For each month: the winners, losers and all ranked stocks (same rule as the main tests)."""
    signals = pd.DataFrame({t: m[MAIN] for t, m in stocks.items()})
    next_returns = pd.DataFrame({t: m['next_1m'] for t, m in stocks.items()})
    groups = {}
    for month in signals.index:
        if next_returns.loc[month].isna().all():
            continue
        ranked = signals.loc[month].dropna().sort_values()
        n = number_per_side(len(ranked))
        if len(ranked) < 2 * n:
            continue
        groups[month] = dict(winners=list(ranked.index[-n:]), losers=list(ranked.index[:n]),
                             all=list(ranked.index))
    return groups


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    pd.set_option('display.max_rows', 200)

    index_m, pool = load_pool()
    trading_days = trading_days_per_month(load_index())
    chars = characteristics(pool, index_m, trading_days)
    universes = {'Fixed 13': fixed_universe(pool), f'Rule-based {K_MAIN}': restrict(pool, membership(pool, K_MAIN))}

    rows_A, rows_B, rows_sector = [], [], []
    for universe, stocks in universes.items():
        groups = group_members(stocks)

        # A) average characteristics by group (cross-sectional median, then time-series mean)
        for name in CHARACTERISTICS:
            by_group = {g: pd.Series({month: chars[name].loc[month, members[g]].median()
                                      for month, members in groups.items()})
                        for g in ['winners', 'losers', 'all']}
            difference = (by_group['losers'] - by_group['all']).dropna()
            mean, t, p = mean_test(difference)
            rows_A.append(dict(universe=universe, characteristic=name,
                               winners=by_group['winners'].mean(), losers=by_group['losers'].mean(),
                               all_stocks=by_group['all'].mean(), losers_minus_all=mean,
                               t_NW=t, p=p, sig=stars(p), months=len(difference)))

        # B) which stocks and sectors were losers
        loser_count = pd.Series([t for members in groups.values() for t in members['losers']]).value_counts()
        ranked_count = pd.Series([t for members in groups.values() for t in members['all']]).value_counts()
        for ticker in ranked_count.index:
            rows_B.append(dict(universe=universe, ticker=ticker, sector=SECTORS.get(ticker, ''),
                               months_ranked=int(ranked_count[ticker]),
                               months_as_loser=int(loser_count.get(ticker, 0)),
                               share_of_ranked_months_as_loser=loser_count.get(ticker, 0) / ranked_count[ticker]))
        by_sector = pd.DataFrame(rows_B)
        by_sector = by_sector[by_sector['universe'] == universe].groupby('sector')[['months_ranked', 'months_as_loser']].sum()
        by_sector['share_of_loser_slots'] = by_sector['months_as_loser'] / by_sector['months_as_loser'].sum()
        by_sector['share_of_ranked_slots'] = by_sector['months_ranked'] / by_sector['months_ranked'].sum()
        for sector, r in by_sector.iterrows():
            rows_sector.append(dict(universe=universe, sector=sector, **r.to_dict()))

    # C) exploratory: loser effect on market and an illiquid-minus-liquid spread
    eligible_illiquidity = chars['amihud'].where(pd.DataFrame({t: m['liquid'] & m['adv_12m'].notna()
                                                               for t, m in pool.items()}))
    next_returns = pd.DataFrame({t: m['next_1m'] for t, m in pool.items()})
    iml = {}
    for month in eligible_illiquidity.index:
        values = eligible_illiquidity.loc[month].dropna()
        if len(values) < 9 or next_returns.loc[month].isna().all():
            continue
        ordered = values.sort_values()
        third = len(ordered) // 3
        iml[month] = (next_returns.loc[month, ordered.index[-third:]].mean()
                      - next_returns.loc[month, ordered.index[:third]].mean())
    iml = pd.Series(iml)

    rows_C = []
    for universe, stocks in universes.items():
        from portfolios import leg_returns
        legs = leg_returns(stocks, MAIN)
        loser_effect = legs['all'] - legs['losers']
        rf = rf_for_holding_month(loser_effect.index)
        data = pd.DataFrame({'loser_effect': loser_effect,
                             'market_excess': index_m['next_1m'].reindex(loser_effect.index) - rf,
                             'IML': iml.reindex(loser_effect.index)}).dropna().astype(float)
        fit = sm.OLS(data['loser_effect'], sm.add_constant(data[['market_excess', 'IML']])).fit(
            cov_type='HAC', cov_kwds={'maxlags': 3})
        rows_C.append(dict(universe=universe, alpha_annual=fit.params['const'] * 12,
                           t_alpha=fit.tvalues['const'], p_alpha=fit.pvalues['const'],
                           beta_market=fit.params['market_excess'], t_market=fit.tvalues['market_excess'],
                           beta_IML=fit.params['IML'], t_IML=fit.tvalues['IML'], months=len(data),
                           IML_annual_mean=data['IML'].mean() * 12))

    A, B, S, C = pd.DataFrame(rows_A), pd.DataFrame(rows_B), pd.DataFrame(rows_sector), pd.DataFrame(rows_C)
    print('=== A) Characteristics of winners, losers and all stocks (losers - all tested) ===')
    print(A.round(4).to_string(index=False))
    print('\n=== B) Sectors: share of loser slots vs share of all ranked slots ===')
    print(S.round(3).to_string(index=False))
    print('\n=== C) EXPLORATORY: loser effect on market excess return and illiquid-minus-liquid spread ===')
    print(C.round(4).to_string(index=False))
    with pd.ExcelWriter('loser_characteristics.xlsx') as xw:
        A.to_excel(xw, sheet_name='A_characteristics', index=False)
        B.to_excel(xw, sheet_name='B_stocks', index=False)
        S.to_excel(xw, sheet_name='B_sectors', index=False)
        C.to_excel(xw, sheet_name='C_exploratory_regression', index=False)
    print('\nSaved loser_characteristics.xlsx')
