# Regime & Range-Adjusted Relative Strength (RR-RS)

Point-to-point relative strength (today's close vs one past date) has a blind spot: it ignores everything that happened in between. RR-RS fixes this by measuring each stock **inside the market's own swing legs**. It asks how far the stock fell when the market fell, and how hard it ran when the market ran.

The reference implementation ranks the 12 Nifty PSU Bank stocks against Nifty 500.

## Method

1. **Market legs:** a zigzag on the Nifty 500 close (6% reversal) over the last 126 sessions splits the window into down legs and up legs. If there's no down leg, it falls back to splitting up days from down days.
2. **Sub-scores per stock**

| Block | Weight | Metrics |
|---|---|---|
| Bear-RS | 30% | DR = stock return − index return over down legs; DDR = stock MaxDD − index MaxDD |
| Bull-RS | 25% | UO = stock return − index return over up legs; RHE = stock (HH/LL − 1) − index (HH/LL − 1) |
| Trend | 20% | O'Neil weighted ROC: 0.4 × ROC63 + 0.2 × (ROC126 + ROC189 + ROC252) |
| Position | 15% | RP63 = (Close − LL) / (HH − LL) |
| RS line | 10% | Stock/index ratio vs its 126-day high |

   Legs are weighted 50 / 30 / 20, most recent first.

3. **Ranking:** each metric is percentile-ranked (1–99) across the universe, then blended and re-ranked into RR-RS.
4. **Filters (applied after ranking):**
   - Knock out stocks more than 15% below their 63-day high.
   - Knock out stocks whose 63-day MaxDD is worse than 2.5× the index's **and** worse than −10%.
   - Leaders need both Bear-RS ≥ 60 and Bull-RS ≥ 60. This screens out low-beta defensives and pure high-beta bouncers.
   - Tie-break by days the stock bottomed before the index.
5. **Setup flag:** close within 4% of a rising 20-SMA, with 10-day average volume below the 50-day average.

## Usage

```bash
pip install -r requirements.txt
python rr_rs_psu.py                 # downloads ~2 years of daily data via yfinance
python rr_rs_psu.py --csv-dir data  # or read data/<SYMBOL>.csv (Date,Open,High,Low,Close,Volume)
```

For CSV mode, name the benchmark files `NIFTY500.csv` and `NIFTYPSUBANK.csv`. To cover another sector, edit `STOCKS` and the industry index symbol.

Output is a printed table plus `rr_rs_psu_banks.csv`.

## Caveats

- Weights and thresholds are starting assumptions, not backtested values.
- In a 12-stock universe the percentiles are coarse, so read the raw spreads too.
- For research only. Not investment advice.
