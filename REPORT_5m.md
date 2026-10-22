# ICT Concepts Backtest — 5-MINUTE ES & NQ + Randomization Test

**Date:** 2026-10-07
**Data:** Yahoo Finance continuous front-month futures `ES=F` / `NQ=F`, **5-minute bars**,
2026-07-28 → 2026-10-06 (~60 days, 13,606 bars each, full 24h Globex session).
**Split:** In-sample (IS) = first half (~30 days), Out-of-sample (OOS) = second half.

> This is the shortest-timeframe companion to the daily (`REPORT.md`) and 1-hour
> (`REPORT_intraday.md`) studies. Same ICT model, engine, and variants; only the data
> timeframe changes. Base parameters are ATR-normalized (scale-free), so the same values
> are used. This study adds a **randomization test** to ask whether the strategy's
> performance is distinguishable from pure noise.

---

## 1. Why 5-minute bars

Yahoo's free 5-minute history is capped at ~60 days, so this is a ~2-month sample.
That is too short for a robust standalone conclusion, but it is long enough to (a) see
the cost dynamics at the shortest practical timeframe and (b) run a meaningful
randomization test.

---

## 2. Base model results (5m, ~60 days)

| Symbol | Period | Trades | Win % | PF (net) | Avg R (gross) | Max DD | Total Return |
|--------|--------|-------:|------:|---------:|--------------:|-------:|-------------:|
| ES | IS | 70 | 18.6 | 0.09 | −0.07 | −81.9% | −81.9% |
| ES | OOS | 91 | 16.5 | 0.05 | +0.01 | −88.6% | −88.6% |
| **ES** | **ALL** | **161** | **17.4** | **0.07** | **−0.03** | **−95.6%** | **−95.6%** |
| NQ | IS | 91 | 14.3 | 0.06 | +0.05 | −83.8% | −83.2% |
| NQ | OOS | 96 | 11.5 | 0.04 | +0.06 | −88.5% | −88.4% |
| **NQ** | **ALL** | **187** | **12.8** | **0.06** | **+0.06** | **−98.1%** | **−98.0%** |

Buy & hold (same ~60-day window): ES +12.5% · NQ +12.5% (approx.).

**The base model loses ~96–98% of equity in 60 days.** This is the worst of the three
timeframes by far.

---

## 3. Why it loses so much: the cost burden explodes at 5m

Decomposing gross P&L vs. transaction cost:

| Symbol | Gross P&L | Cost | Net | Gross R/trade | **Cost R/trade** | Avg stop width |
|--------|----------:|-----:|----:|--------------:|-----------------:|---------------:|
| ES | −$1,168 | $94,451 | −$95,619 | −0.023 | **1.82** | 0.062% of price |
| NQ | −$2,192 | $95,856 | −$98,048 | −0.043 | **1.89** | 0.101% of price |

The 5-minute stops are extremely tight (~0.06–0.10% of price). With 1% risk per trade,
that implies a very large notional, so the round-trip cost is **~1.8R per trade**. The
gross edge is ≈0, so every trade loses ~1.8R to costs. ~160–190 trades × ~1.85R ≈ the
observed ~96–98% loss.

**The gross edge that appeared on 1h ES (+0.25R) is gone on 5m (≈0).** It does not
persist to the shorter timeframe.

---

## 4. Randomization test: real data vs. randomly generated data

**Method.** For each symbol we generate 300 synthetic OHLC series that share the real
data's return distribution (bootstrap of the empirical 5m log-returns, so volatility and
fat tails are preserved) but have **no temporal structure**, with wicks sampled from the
empirical wick distribution. The identical strategy is run on each. The real-data result
is then located inside the null distribution.

| Metric | ES real | ES random (mean / median) | NQ real | NQ random (mean / median) |
|--------|--------:|--------------------------:|--------:|--------------------------:|
| Total return | −95.6% | −96.7% / −96.9% | −98.0% | −98.2% / −98.3% |
| Profit factor | 0.07 | 0.12 / 0.11 | 0.06 | 0.08 / 0.07 |
| Avg R (gross) | −0.03 | +0.04 / — | +0.06 | +0.03 / — |

**Where the real data sits in the null distribution:**

| Symbol | Real return percentile | Real PF percentile | p-value (return) | p-value (PF) |
|--------|-----------------------:|-------------------:|-----------------:|-------------:|
| ES | 84th | 9th | 0.176 | 0.960 |
| NQ | 70th | 37th | 0.362 | 0.804 |

**Interpretation.** The strategy's performance on real data is **statistically
indistinguishable from its performance on pure random data**:
- Real and random total returns are essentially identical (−95.6% vs −96.7% for ES;
  −98.0% vs −98.2% for NQ). The real-data return sits comfortably inside the random
  distribution (p ≈ 0.18 / 0.36 — not significant).
- Real and random gross expectancy are both ≈0 (real −0.03/+0.06 vs random +0.04/+0.03).
- The real-data profit factor is, if anything, *worse* than the random mean (ES at the
  9th percentile).

**Conclusion of the randomization test: there is no edge on 5m bars.** The strategy's
large loss is not a special failure of the ICT logic — it is exactly what you get from
running the same cost-incurring strategy on noise. The strategy is a cost-generating
machine at this timeframe; it adds no predictive value over random data.

---

## 5. Ablations / management / sensitivity (5m, full period)

- **Ablations:** no variant is net-positive. The best (least-bad) is `base+trend`
  (ES −23.3%, NQ −26.3%) with only 13–19 trades — still a large loss. Removing the sweep
  or FVG more than doubles the trade count and the loss. CHoCH/BOS/structure-break
  filters again produce ~0 trades.
- **Position management:** breakeven-at-1R, partials, and fixed-R targets all lose
  ~95–99%. No exit change helps when the cost per trade is ~1.8R.
- **Sensitivity:** the whole `disp_atr × sweep_lookback` grid loses ~90–99%. No
  profitable region. Not a tuning problem.

---

## 6. Plots

In `results_5m/`:
- `equity_ES_base.png` / `equity_NQ_base.png` — real-data equity vs. buy & hold.
- `perm_hist_ES.png` / `perm_hist_NQ.png` — total-return and profit-factor histograms of
  the 300 random datasets with the real-data value marked (red line).
- `perm_fan_ES.png` / `perm_fan_NQ.png` — equity fan: real-data curve (red) vs. 40 random
  curves (gray). The real curve is indistinguishable from the random fan.
- `price_trades_ES.png` / `price_trades_NQ.png` — 5m price with entry/exit markers.

---

## 7. Cross-timeframe summary

| Timeframe | Sample | ES gross R/trade | ES cost R/trade | ES net | NQ gross R/trade | NQ net |
|-----------|--------|-----------------:|----------------:|-------:|-----------------:|-------:|
| Daily | 26 y | −0.27 | ~0.1 | − (PF 0.57) | −0.26 | − (PF 0.60) |
| 1-hour | 2.4 y | **+0.25** | 0.37 | −18.7% | −0.08 | −69.4% |
| 5-minute | 60 d | ≈0 | **1.82** | −95.6% | ≈0 | −98.0% |

**Pattern:** as the timeframe shortens, the (marginal) gross edge shrinks toward zero
while the cost-per-trade (in R terms) explodes, because tighter stops inflate the notional
per unit of risk. The only genuine signal found anywhere is the small 1h-ES gross edge
(+0.25R), which is (a) smaller than its cost, and (b) absent on 5m.

---

## 8. Conclusion

**On 5-minute bars the ICT model has no edge, and the randomization test proves it:**
its performance is statistically indistinguishable from running the same strategy on
randomly generated data. Both lose ~96–98% in 60 days, driven by a ~1.8R-per-trade cost
burden against a ≈0 gross edge.

### Bottom line across all three timeframes
The ICT sweep→displacement→FVG model has **no robust, tradeable edge** on ES/NQ at daily,
1-hour, or 5-minute resolution. The single interesting result — a small, persistent gross
edge on 1h ES — is not tradeable after costs and does not survive to 5m. The concepts show
at most a hint of predictive power, and nowhere enough to deploy mechanically.

### Caveats
- **60 days only** (the max free 5m history). Too short for a robust standalone
  conclusion; the randomization test is the more reliable evidence here.
- **Continuous front-month futures** include roll gaps.
- Costs are **conservative** (4 bps ES / 8 bps NQ round trip). Even at zero cost, the 5m
  gross edge is ≈0, so the model would still not be profitable.

---

## Files
- `run_5m.py` — 5m runner + randomization test (reuses `ict.py` / `strategy.py` / `engine.py`)
- `results_5m/` — summary_base.csv, ablations.csv, management.csv, sensitivity.csv,
  randomization.csv, trades_*.csv, equity_*.png, perm_hist_*.png, perm_fan_*.png,
  price_trades_*.png