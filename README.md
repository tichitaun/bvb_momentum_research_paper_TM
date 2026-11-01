# Momentum and Mean Reversion on the Bucharest Stock Exchange, 2015–2025

Code for the paper. Every table and figure is produced by these scripts from the raw data,
with one command.

## Main findings

- Strong **cross-sectional momentum** on the BVB: past winners beat past losers by about
  20–25% per year (12-1 signal), robust to sectors, single stocks, costs and multiple testing.
- At least half of it comes from **past losers**, which lagged the average stock in eight or
  nine of the ten years. A long-only portfolio that simply **avoids the losers** beat BET-TR
  after trading costs, with similar risk.
- The same tests in **Greece, Poland and Germany** find no such effect: Romania is an exception.

## Quick start

From an empty folder containing these scripts:

1. **Install the packages**
   ```
   pip install -r requirements.txt
   ```
2. **Download the 32 stocks from Yahoo Finance**
   ```
   python download_pool.py
   ```
3. **Download BET-TR by hand** from Investing.com (BET Total Return, daily, January 2015 to
   December 2025) and save it in the same folder as
   `Bucharest_Total_Return_Historical_Data.xlsx`, with columns `Date` and `Price`.
   (BET-TR is not available on Yahoo Finance.)
4. **Run the whole analysis**
   ```
   python run_all.py
   ```
   All 8 automatic checks must PASS. The full output is saved to `run_all_log.txt`.

Steps 2 and 3 are only needed once. To reproduce the paper's numbers exactly, use the same
data files: `data_manifest.csv` lists their dates and SHA-256 hashes. Yahoo Finance revises
its adjusted prices over time, so a new download may give slightly different results.

## Data

| Input | Source | How |
|---|---|---|
| `<TICKER>_historical_data.csv` (32 stocks) | Yahoo Finance, daily, raw and adjusted close | `python download_pool.py` |
| `Bucharest_Total_Return_Historical_Data.xlsx` | Investing.com, BET Total Return index, daily | manual download (columns `Date`, `Price`) |
| Risk-free rate | National Bank of Romania policy rate | in `common.py` (`BNR_CHANGES`) |
| Dividend corrections | company filings, BVB, Central Depository | in `common.py` (`CORRECTIONS`) |

The data are not included in this repository (licensing). `environment.txt` lists the
package versions used for the paper.

## What `run_all.py` does

| Step | Script | Produces (paper) |
|---|---|---|
| 1 | `make_manifest.py` | `data_manifest.csv`, `environment.txt` |
| 2 | `data_audit.py` | `data_audit.xlsx` (Appendix B) |
| 3 | `checks.py` | 8 automatic timing and accounting tests, all must PASS |
| 4 | `table1.py` | `table1.xlsx` (Table 1) |
| 5 | `analysis.py` | `results_core.xlsx`, `results_extended.xlsx` (Tables 2, 3) |
| 6 | `robustness.py` | `robustness_*.xlsx`, `wml_chart_*.png` (Tables 3, 4, Figure 1) |
| 7 | `long_only.py` | `long_only.xlsx` (Table 5, cost levels) |
| 8 | `concentration.py` | `concentration.xlsx` (Table 5) |
| 9 | `universe.py` | `universe.xlsx` (Tables 3, 5, A1) |
| 10 | `walk_forward.py` | `walk_forward.xlsx` (Table 6, Figure 3) |
| 11 | `costs.py` | `costs.xlsx` (Table 7) |
| 12 | `losers.py` | `losers.xlsx`, `losers_chart.png` (Table 8, Figures 4, 5) |
| 13 | `inference.py` | `inference.xlsx` (Table D1) |
| 14 | `sensitivity.py` | `sensitivity.xlsx` (results without the manual data corrections) |
| 15 | `loser_characteristics.py` | `loser_characteristics.xlsx` (what kind of stocks the losers are) |
| 16 | `charts_1000_lei.py` | `chart_*.png`, `values_1000_lei.xlsx` (Figures 2, A1) |

Two files are shared by all scripts:

- `common.py` – settings, data loading and cleaning, monthly data, universes, statistics, charts
- `portfolios.py` – ranking stocks and building portfolios month by month

### Cross-market comparison (Table 10, Figures 6–7)

In the `markets/` folder (self-contained, run separately):

```
python markets_download.py     # once: downloads Romania, Greece, Poland and Germany into markets/data/
python markets_analysis.py
```

## Conventions

- **Timing.** Each monthly row is a formation month *t*. Signals use prices up to the end of
  *t* (up to *t*−1 for the 12-1 signal); `next_1m` is the return from the end of *t* to the
  end of *t*+1. Stocks are chosen with information known at *t* only (`checks.py` tests this).
- **Calendar.** One row per calendar month; a month without trades keeps the last price.
  Calendar-year figures use the year in which each return is earned (*t*+1).
- **Liquidity filter.** A stock can be chosen in month *t* only if it traded on at least 80%
  of the exchange's trading days in *t*.
- **Rule-based universe.** Each month, the 15 stocks with the highest average daily traded
  value over months *t*−11 to *t*, among stocks with 12 months of history that pass the filter.
- **Costs.** A cost *c* is charged per leu bought or sold (one-way) on the turnover
  Σ|new weight − drifted weight|. Stock-specific costs use the Abdi and Ranaldo (2017) spread
  of months *t*−2 to *t*; a missing estimate uses the stock's median up to *t*, or 2%.
- **Walk-forward.** The strategy for year *y* is chosen at the end of January of *y*, using
  only returns already earned.
- **Random numbers.** The bootstrap in `inference.py` uses seed 42.

## Known limitations

The stock pool contains only companies still listed in 2025 (no history for delisted
companies on Yahoo Finance), so survivorship bias is reduced but not eliminated. Four
corporate actions were corrected by hand (`CORRECTIONS` in `common.py`, Appendix B).
