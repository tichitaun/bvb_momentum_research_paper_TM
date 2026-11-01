"""
Configuration for the cross-market comparison: Romania, Greece, Poland, Germany.
Same period, same rules, same tests in every market.

Market status 2015-2025 (for the paper):
  Romania  - FTSE Frontier, then Secondary Emerging from Sep 2020; MSCI Frontier
  Greece   - Emerging (FTSE Advanced Emerging, MSCI Emerging) for the whole period
  Poland   - FTSE Developed from Sep 2018, MSCI Emerging ("in between")
  Germany  - Developed
"""

START, END = '2015-01-01', '2026-01-01'   # yfinance: END is exclusive -> data to 31 Dec 2025

K_UNIVERSE = 15          # each month: the 15 most liquid stocks (12-month average daily traded value)
K_ROBUST = 10            # robustness: 10 most liquid
FRACTION = 0.30          # winners = top 30%, losers = bottom 30%
MIN_TRADED = 0.80        # stock must trade on >= 80% of the market's trading days in the month
COMMISSION = 0.0020      # commission + fees per leu/euro/zloty traded, same in every market
FLAG_THRESHOLD = 0.15    # dividend-adjustment detector (see data audit)

# Risk-free rates: policy rate (% per year) from the month in which it took effect.
# NBP 2023 and May-November 2025 decisions checked against NBP press releases;
# the December 2025 cut to 4.00% and the 2015 values still need checking on nbp.pl / ecb.europa.eu.
BNR = {'2015-01': 2.50, '2015-02': 2.25, '2015-04': 2.00, '2015-05': 1.75,
       '2018-01': 2.00, '2018-02': 2.25, '2018-05': 2.50, '2020-03': 2.00, '2020-05': 1.75,
       '2020-08': 1.50, '2021-01': 1.25, '2021-10': 1.50, '2021-11': 1.75, '2022-01': 2.00,
       '2022-02': 2.50, '2022-04': 3.00, '2022-05': 3.75, '2022-07': 4.75, '2022-08': 5.50,
       '2022-10': 6.25, '2022-11': 6.75, '2023-01': 7.00, '2024-07': 6.75, '2024-08': 6.50}
# ECB deposit facility rate (Greece and Germany)
ECB = {'2015-01': -0.20, '2015-12': -0.30, '2016-03': -0.40, '2019-09': -0.50, '2022-07': 0.00,
       '2022-09': 0.75, '2022-11': 1.50, '2022-12': 2.00, '2023-02': 2.50, '2023-03': 3.00,
       '2023-05': 3.25, '2023-06': 3.50, '2023-08': 3.75, '2023-09': 4.00, '2024-06': 3.75,
       '2024-09': 3.50, '2024-10': 3.25, '2024-12': 3.00, '2025-02': 2.75, '2025-03': 2.50,
       '2025-04': 2.25, '2025-06': 2.00}
# National Bank of Poland reference rate
NBP = {'2015-01': 2.00, '2015-03': 1.50, '2020-03': 1.00, '2020-04': 0.50, '2020-05': 0.10,
       '2021-10': 0.50, '2021-11': 1.25, '2021-12': 1.75, '2022-01': 2.25, '2022-02': 2.75,
       '2022-03': 3.50, '2022-04': 4.50, '2022-05': 5.25, '2022-06': 6.00, '2022-07': 6.50,
       '2022-09': 6.75, '2023-09': 6.00, '2023-10': 5.75, '2025-05': 5.25, '2025-07': 5.00,
       '2025-09': 4.75, '2025-10': 4.50, '2025-11': 4.25, '2025-12': 4.00}

# Companies tried but without usable Yahoo Finance history (left out of the lists below):
#   Greece : OPAP (renamed Allwyn; its full history is under ALWN, which is included),
#            Mytilineos (MYTIL; only the 2025 Metlen listing MTLN exists), Alpha Bank before 2025
#   Poland : Santander Bank Polska (SPL), CCC (renamed MDV, which is included),
#            Lotos (LTS) and PGNiG (PGN), both delisted in 2022 after merging into Orlen
#   Germany: Covestro (1COV), Wirecard and Linde AG (delisted)
# The delisted companies are a source of survivorship bias that cannot be removed with Yahoo data.

MARKETS = {
    'Romania': dict(
        level=1, suffix='.RO', rates=BNR, currency='lei',
        tickers=['TLV', 'BRD', 'SNG', 'SNN', 'SNP', 'TEL', 'TGN', 'ALR', 'ATB', 'ARS', 'DIGI', 'M',
                 'SFG', 'EL', 'COTE', 'OIL', 'RRC', 'BVB', 'TRP', 'VNC', 'ROCE', 'ELMA', 'TBM',
                 'SNO', 'IMP', 'ONE', 'WINE', 'AQ', 'TTS', 'H2O', 'BIO', 'BNET'],
        # verified corrections (see paper, Appendix B): (ticker, date) -> dividend or 'raw'
        corrections={('SNN', '2018-12-21'): 1.61, ('ALR', '2019-01-08'): 0.45756,
                     ('ROCE', '2022-12-08'): 0.005, ('BNET', '2021-07-20'): 'raw'}),
    'Greece': dict(
        level=2, suffix='.AT', rates=ECB, currency='euro',
        tickers=['ETE', 'EUROB', 'ALPHA', 'TPEIR', 'HTO', 'MTLN', 'PPC', 'MOH', 'ELPE',
                 'BELA', 'TITC', 'GEKTERNA', 'LAMDA', 'VIO', 'CENER', 'EXAE', 'AEGN', 'ADMIE',
                 'ALWN',   # Mytilineos before the 2025 move to Metlen; OPAP renamed Allwyn
                 'EYDAP', 'FOYRK', 'SAR', 'OLTH', 'PLAKR', 'QUEST', 'INTRK', 'ELLAKTOR', 'AIA',
                 'OPTIMA'],
        # Ellaktor distributions verified on the Athens Exchange issuer pages (cash distribution list)
        corrections={('ELLAKTOR', '2024-07-22'): 0.50,      # capital return
                     ('ELLAKTOR', '2025-03-24'): 0.851945,  # capital return
                     ('ELLAKTOR', '2025-12-22'): 0.5029}),  # interim dividend
    'Poland': dict(
        level=3, suffix='.WA', rates=NBP, currency='zloty',
        tickers=['PKO', 'PEO', 'PZU', 'KGH', 'PKN', 'PGE', 'LPP', 'CDR', 'DNP', 'ALE', 'MBK',
                 'CPS', 'OPL', 'KRU', 'JSW', 'PCO', 'KTY', 'ACP', 'TPE', 'ENA', 'BDX', 'MIL',
                 'ALR', 'ATT', 'XTB', 'BHW', 'CAR', 'DOM',
                 'MDV',    # CCC after renaming
                 # still-listed companies that were large WIG20/mWIG40 members during 2015-2025
                 'EUR', 'LWB', 'GPW', 'PKP', 'ECH', 'GTC'],
        corrections={}),
    'Germany': dict(
        level=4, suffix='.DE', rates=ECB, currency='euro',
        tickers=['SAP', 'SIE', 'ALV', 'DTE', 'AIR', 'MBG', 'BMW', 'BAS', 'BAYN', 'MUV2', 'DBK',
                 'IFX', 'ADS', 'VOW3', 'DHL', 'RWE', 'EOAN', 'DB1', 'HEN3', 'BEI', 'FRE', 'FME',
                 'HEI', 'CON', 'MRK', 'SHL', 'VNA', 'RHM', 'MTX', 'CBK', 'PAH3', 'ZAL', 'SY1',
                 'QIA', 'HNR1', 'BNR',
                 # still-listed companies that were DAX members during 2015-2025 (or joined it):
                 # added so the pool is not limited to the 2025 index (reduces survivorship bias).
                 # Delisted former members (e.g. Wirecard, Linde AG) have no Yahoo data.
                 'LHA', 'TKA', 'PSM', 'LXS', 'PUM', 'SRT3', 'HFG', 'DTG', 'ENR', 'P911', 'DWNI'],
        corrections={}),
}
