"""
costs.py - realistic, stock-specific trading costs and capacity (paper Table 7).

1) Bid-ask spread of every stock, every month, estimated from daily high, low and close
   prices with the Abdi and Ranaldo (2017) estimator:
       c   = log(close),   eta = (log(high) + log(low)) / 2
       S^2 = 4 * average of (c_t - eta_t) * (c_t - eta_t+1)   over pairs of days in the month
       S   = sqrt(S^2), with negative values set to 0
   Then averaged over months t-2..t, so a trade at the end of month t only uses the past.

2) Cost of each trade (per leu bought or sold, one-way), five scenarios:
       flat 0.5%, flat 1%, flat 2%      - the same cost for every stock
       realistic    - half the stock's spread + 0.20% commission and fees
       pessimistic  - the full spread + 0.40%

3) Capacity: the largest portfolio (lei) for which every trade stays below 10% of the
   stock's average daily traded value in that month.

Saves costs.xlsx.
"""
import numpy as np
import pandas as pd

from common import (MAIN, K_MAIN, load_pool, load_index, trading_days_per_month,
                    fixed_universe, rule_based_universe, rf_for_holding_month, evaluate)
from portfolios import build_portfolio, choose_group, choose_top

# scenario name -> (share of the spread paid, commission). None = flat cost, no spread.
SCENARIOS = {'flat 0.5%': (None, 0.005),
             'flat 1%': (None, 0.010),
             'flat 2%': (None, 0.020),
             'realistic': (0.5, 0.002),
             'pessimistic': (1.0, 0.004)}
FALLBACK_SPREAD = 0.02       # used if a stock has no spread estimate up to that month
MAX_SHARE_OF_VOLUME = 0.10   # a trade may be at most 10% of the stock's daily traded value
IMPUTED = []                 # (month, ticker) where a missing spread had to be filled


def monthly_spread_and_traded_value(ticker, trading_days):
    """Estimated spread and average daily traded value (lei) of one stock, per month."""
    df = pd.read_csv(f'{ticker}_historical_data.csv', parse_dates=['Date'])
    df = df[df['Volume'] > 0].copy()

    # the estimator assumes low <= close <= high; widen the range only if a data error
    # puts the close outside it
    high = df[['High', 'Close']].max(axis=1)
    low = df[['Low', 'Close']].min(axis=1)

    df['c'] = np.log(df['Close'])
    df['eta'] = (np.log(high) + np.log(low)) / 2
    df['YearMonth'] = df['Date'].dt.to_period('M')
    df['eta_next_day'] = df.groupby('YearMonth')['eta'].shift(-1)       # next day, same month
    df['product'] = (df['c'] - df['eta']) * (df['c'] - df['eta_next_day'])

    spread_squared = 4 * df.groupby('YearMonth')['product'].mean()
    spread = np.sqrt(spread_squared.clip(lower=0))

    value = (df['Close'] * df['Volume']).groupby(df['YearMonth']).sum()
    avg_daily_value = value / trading_days.reindex(value.index)
    return spread, avg_daily_value


def monthly_costs(trades, spreads, scenario):
    """Trading cost of each month = sum over traded stocks of |weight change| x cost per leu."""
    spread_share, commission = SCENARIOS[scenario]
    median_so_far = spreads.expanding().median()        # each stock's median up to month t

    costs = {}
    for month, weight_changes in trades.items():
        if spread_share is None:                        # flat cost
            costs[month] = weight_changes.sum() * commission
            continue

        cost_per_leu = {}
        for ticker in weight_changes.index:
            spread = spreads.at[month, ticker] if month in spreads.index and ticker in spreads.columns else np.nan
            if np.isnan(spread):
                # no estimate this month: use the stock's own past median, else 2%
                if month in median_so_far.index and ticker in median_so_far.columns:
                    spread = median_so_far.at[month, ticker]
                if np.isnan(spread):
                    spread = FALLBACK_SPREAD
                if scenario == 'realistic':
                    IMPUTED.append((month, ticker))
            cost_per_leu[ticker] = spread_share * spread + commission

        costs[month] = (weight_changes * pd.Series(cost_per_leu)).sum()
    return pd.Series(costs)


def capacity(trades, traded_value):
    """Largest portfolio (lei) such that every trade <= 10% of the stock's daily traded value."""
    limits = {}
    for month, weight_changes in trades.items():
        if month not in traded_value.index or weight_changes.empty:
            continue
        # a trade of size (portfolio x weight change) must be <= 10% x daily value
        per_stock = MAX_SHARE_OF_VOLUME * traded_value.loc[month, weight_changes.index] / weight_changes
        limits[month] = per_stock.min()
    return pd.Series(limits)


if __name__ == '__main__':
    pd.set_option('display.width', 220)
    pd.set_option('display.max_rows', 300)

    index_m, pool = load_pool()
    trading_days = trading_days_per_month(load_index())

    # 1) spreads and traded value of every stock
    spread_by_stock, value_by_stock = {}, {}
    for ticker in pool:
        spread_by_stock[ticker], value_by_stock[ticker] = monthly_spread_and_traded_value(ticker, trading_days)
    raw_spreads = pd.DataFrame(spread_by_stock)
    spreads = raw_spreads.rolling(3, min_periods=1).mean()      # months t-2..t
    traded_value = pd.DataFrame(value_by_stock)

    recent = raw_spreads[raw_spreads.index >= pd.Period('2023-01', 'M')]
    spread_table = pd.DataFrame({
        'avg_spread_2015_2025': raw_spreads.mean(),
        'avg_spread_2023_2025': recent.mean(),
        'cost_per_trade_realistic': raw_spreads.mean() * 0.5 + SCENARIOS['realistic'][1],
        'avg_daily_value_2023_2025_lei': traded_value[traded_value.index >= pd.Period('2023-01', 'M')].mean().round(0),
    }).sort_values('avg_spread_2015_2025')
    print('=== 1) Estimated bid-ask spread per stock (Abdi-Ranaldo) ===')
    print(spread_table.round(4).to_string())

    # 2) every strategy under every cost scenario
    universes = {'Fixed 13': fixed_universe(pool), f'Rule-based {K_MAIN}': rule_based_universe(pool)}
    strategies = {'Winners top 30%': choose_group('winners'), 'Top 1': choose_top(1),
                  'Top 2': choose_top(2), 'Top 3': choose_top(3),
                  'Equal-weight all': choose_group('all'), 'Losers bottom 30%': choose_group('losers')}

    performance_rows, capacity_rows = [], []
    for universe_name, stocks in universes.items():
        months = build_portfolio(stocks, MAIN, choose_group('winners')).returns.index
        bet = index_m['next_1m'].reindex(months)
        rf = rf_for_holding_month(months)

        for strategy_name, choose in strategies.items():
            p = build_portfolio(stocks, MAIN, choose)
            gross = p.returns.reindex(months)
            for scenario in SCENARIOS:
                cost = monthly_costs(p.trades, spreads, scenario).reindex(months).fillna(0)
                row = evaluate(gross - cost, bet, rf, f'{universe_name} | {strategy_name} | {scenario}')
                row['annual_cost_drag'] = cost.mean() * 12
                performance_rows.append(row)

            cap = capacity(p.trades, traded_value)
            capacity_rows.append(dict(universe=universe_name, strategy=strategy_name,
                                      median_capacity_lei=cap.median(),
                                      median_capacity_2023_2025_lei=cap[cap.index >= pd.Period('2023-01', 'M')].median(),
                                      worst_10pct_months_lei=cap.quantile(0.10)))
        performance_rows.append(evaluate(bet, bet, rf, f'{universe_name} | BET-TR'))

    performance = pd.DataFrame(performance_rows).drop(columns=['annual_turnover'])
    print('\n=== 2) Strategies under the cost scenarios ===')
    print(performance.round(3).to_string(index=False))

    capacities = pd.DataFrame(capacity_rows)
    print(f'\n=== 3) Capacity: largest portfolio with every trade <= {MAX_SHARE_OF_VOLUME:.0%} of daily traded value ===')
    print(capacities.round(0).to_string(index=False))

    print(f'\nSpread estimate missing for {len(IMPUTED)} traded stock-months (realistic scenario); '
          f"filled with the stock's past median, or {FALLBACK_SPREAD:.0%} if none exists.")

    with pd.ExcelWriter('costs.xlsx') as xw:
        spread_table.reset_index(names='ticker').to_excel(xw, sheet_name='1_spreads', index=False)
        performance.to_excel(xw, sheet_name='2_performance', index=False)
        capacities.to_excel(xw, sheet_name='3_capacity', index=False)
        raw_spreads.reset_index(names='month').to_excel(xw, sheet_name='monthly_spreads', index=False)
    print('\nSaved costs.xlsx')
