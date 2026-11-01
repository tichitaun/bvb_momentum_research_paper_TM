"""
run_all.py - run the whole analysis, in order, with one command:

    python run_all.py

The data must already be in this folder (download_pool.py + the BET-TR file).
Every script's output is printed and also saved to run_all_log.txt.
The run stops at the first error.
"""
import glob
import os
import subprocess
import sys
import time

# always work in the folder where this file is saved, wherever it is started from
os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f'Working folder: {os.getcwd()}')

SCRIPTS = [
    'make_manifest.py',    # record the input files and package versions
    'data_audit.py',       # check the dividend adjustments
    'checks.py',           # timing and accounting tests (must all pass)
    'table1.py',           # Table 1: summary statistics
    'analysis.py',         # Tables 2-3: regressions, timing, panel, winners minus losers
    'robustness.py',       # Table 4, Figure 1: sector-neutral, leave-one-out, sub-periods, alpha
    'long_only.py',        # Table 5: long-only winners vs BET-TR, cost levels
    'concentration.py',    # Table 5: Top 1-4
    'universe.py',         # Tables 3, 5, A1: rule-based universe
    'walk_forward.py',     # Table 6, Figure 3: out-of-sample test
    'costs.py',            # Table 7: stock-specific costs and capacity
    'losers.py',           # Table 8, Figures 4-5: winners vs losers, avoid-losers
    'inference.py',        # Table D1: lag sensitivity, confidence intervals, bootstrap
    'sensitivity.py',      # results with and without the hand-made data corrections
    'loser_characteristics.py',  # liquidity, volatility, beta and sectors of the losers
    'charts_1000_lei.py',
    'loser_characteristics.py',
    'sensitivity.py'  # Figures 2 and A1: growth of 1,000 lei
]
MODULES = ['common.py', 'portfolios.py']    # shared code imported by the scripts

# ---- check that everything needed is in this folder before starting
missing = [f for f in SCRIPTS + MODULES if not os.path.exists(f)]
if not os.path.exists('Bucharest_Total_Return_Historical_Data.xlsx'):
    missing.append('Bucharest_Total_Return_Historical_Data.xlsx')
n_csv = len(glob.glob('*_historical_data.csv'))
if n_csv < 13:
    missing.append(f'stock CSV files (found only {n_csv}, expected about 32)')
if missing:
    print('Run this from the folder that contains ALL scripts and ALL data. Missing here:')
    for f in missing:
        print('   -', f)
    sys.exit(1)

# ---- run every script in order
with open('run_all_log.txt', 'w', encoding='utf-8') as log:
    for script in SCRIPTS:
        start = time.time()
        header = f'\n{"=" * 80}\nRUNNING {script}\n{"=" * 80}\n'
        print(header, flush=True)
        log.write(header)

        result = subprocess.run([sys.executable, script], capture_output=True, text=True)
        print(result.stdout)
        log.write(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            log.write(result.stderr)
            print(f'\nSTOPPED: {script} failed. Send me the error above.')
            sys.exit(1)
        print(f'{script} finished in {time.time() - start:.0f} s', flush=True)

print('\nAll scripts finished. Full output saved to run_all_log.txt')
