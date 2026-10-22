# ICT Concepts Backtest — INTRADAY (1-hour) ES & NQ

**Date:** 2026-10-07
**Data:** Yahoo Finance continuous front-month futures `ES=F` / `NQ=F`, **1-hour bars**,
2024-05-14 → 2026-10-06 (~2.4 years, 13,726 bars each, full 24-hour Globex session).
**Split:** In-sample (IS) = first half, Out-of-sample (OOS) = second half (by position, no overlap).

> This is the intraday companion to the daily study (`REPORT.md`). The same ICT model,
> engine, and variant definitions are used; only the data timeframe changes. The base
> parameters are ATR-normalized (scale-free), so the same values are used for a clean
> comparison.

---

## 1. Why 1-hour bars

Yahoo Finance's free intraday history is limited: 1-min (7 days), 5/15-min (60 days),
**1-hour (730 days)**. The 1-hour window is the only intraday timeframe with a usable
sample size, so this study uses 1-hour bars (~2.4 years of full-session data).

---

## 2. Base model results (1h)

| Symbol | Period | Trades | Win % | PF (net) | Avg R (gross) | Max DD | Total Return |
|--------|--------|-------:|------:|---------:|--------------:|-------:|-------------:|
| ES | IS | 79 | 41.8 | 0.91 | **+0.31** | −13.6% | −5.3% |
| ES | OOS | 89 | 40.4 | 0.79 | **+0.22** | −18.5% | −13.1% |
| **ES** | **ALL** | **169** | **40.8** | **0.84** | **+0.25** | **−29.9%** | **−18.7%** |
| NQ | IS | 83 | 33.7 | 0.46 | +0.09 | −33.7% | −33.6% |
| NQ | OOS | 91 | 24.2 | 0.27 | −0.25 | −53.7% | −53.5% |
| **NQ** | **ALL** | **175** | **28.6** | **0.37** | **−0.09** | **−69.4%** | **−69.4%** |

Buy & hold (same 2.4y window): ES +50.3% (max DD −21.1%) · NQ +72.4% (max DD −25.9%).

**The base model loses money in both samples, on both symbols — and far more than the
daily model did.**

---

## 3. The key finding: a real gross edge on ES, eaten by costs

The profit factor and total return are **net of costs**, while the average R is **gross**.
Decomposing ES and NQ into gross P&L vs. transaction cost reveals the story:

| Symbol | Gross P&L | Cost | Net | Gross R/trade | Cost R/trade | Avg stop width |
|--------|----------:|-----:|----:|--------------:|-------------:|---------------:|
| ES | **+$38,090** | $56,826 | −$18,736 | **+0.246** | 0.366 | 0.33% of price |
| NQ | −$7,991 | $61,431 | −$69,422 | −0.075 | 0.577 | 0.40% of price |

And the gross edge is **consistent across IS and OOS** (not a one-period artifact):

| Symbol | IS gross R | OOS gross R | Cost R/trade |
|--------|-----------:|------------:|-------------:|
| ES | **+0.30** | **+0.21** | 0.37 |
| NQ | +0.05 | −0.27 | 0.57 |

**Interpretation:**
1. **ES 1h has a small but real, persistent gross edge** (+0.21 to +0.30 R/trade in both
   halves). The ICT sweep→displacement→FVG setup is *slightly* predictive on 1-hour ES.
2. **The edge is smaller than the cost of trading it.** The 1-hour stops are tight
   (~0.33% of price), so 1% risk per trade implies high notional, and the round-trip cost
   is ~0.37 R/trade (ES) and ~0.58 R/trade (NQ). The gross edge (+0.25R) does not cover it.
3. **NQ 1h has no gross edge at all** — it is a clear loss before costs, and a large loss
   after.

**This is why intraday is worse than daily for this model:** more trades (169 vs 88 over a
far shorter span) and tighter stops push the cost-per-trade (in R terms) above the gross
edge.

---

## 4. Ablations (1h, full period)

| Symbol | Variant | Trades | Win % | PF (net) | Avg R (gross) |
|--------|---------|-------:|------:|---------:|--------------:|
| ES | base | 169 | 40.8 | 0.84 | +0.25 |
| ES | + premium/discount | 157 | 39.5 | 0.82 | +0.24 |
| ES | + trend alignment | 21 | 38.1 | 0.73 | +0.08 |
| ES | + CE entry | 168 | 38.7 | 0.75 | +0.21 |
| ES | **no sweep** | 341 | 38.4 | 0.72 | +0.23 |
| ES | no FVG | 475 | 35.2 | 0.34 | −0.04 |
| ES | no sweep, no FVG | 849 | 63.3 | 0.24 | 0.00 |
| NQ | base | 175 | 28.6 | 0.37 | −0.09 |
| NQ | + trend alignment | 21 | 33.3 | 0.33 | −0.14 |
| NQ | **no sweep** | 375 | 34.7 | 0.43 | +0.09 |
| NQ | no FVG | 496 | 31.2 | 0.22 | −0.10 |
| NQ | no sweep, no FVG | 857 | 31.4 | 0.22 | −0.05 |

(CHoCH / BOS / structure-break filters again produce **0 trades** — too strict.)

**Findings:**
- The win rate is **higher intraday** (40.8% ES vs 27% daily) — the FVG re-entry is more
  likely to be reached within the shorter holding window. But the payoff is smaller and the
  cost per trade is larger, so the net result is worse.
- **No variant is net-positive.** Removing the sweep (`no_sweep`) raises the gross R
  slightly but more than doubles the trade count, so the net loss grows.
- The trend-alignment filter cuts trades to ~21 and is still net-negative.

---

## 5. Position management (1h, full period)

| Symbol | Variant | Trades | Win % | PF (net) | Avg R (gross) |
|--------|---------|-------:|------:|---------:|--------------:|
| ES | base | 169 | 40.8 | 0.84 | +0.25 |
| ES | breakeven @ 1R | 169 | 24.3 | 0.47 | +0.01 |
| ES | partial 50% @ 1R | 169 | 47.3 | 0.50 | +0.09 |
| ES | fixed 1.5R target | 170 | 47.1 | 0.75 | +0.21 |
| ES | fixed 2R target | 168 | 39.9 | 0.72 | +0.16 |
| NQ | base | 175 | 28.6 | 0.37 | −0.09 |
| NQ | breakeven @ 1R | 175 | 16.6 | 0.21 | −0.19 |
| NQ | partial 50% @ 1R | 175 | 28.0 | 0.19 | −0.11 |
| NQ | fixed 1.5R target | 178 | 34.3 | 0.33 | −0.04 |
| NQ | fixed 2R target | 176 | 26.7 | 0.34 | −0.13 |

**Finding:** No exit-management change makes the model net-positive. Breakeven-at-1R
destroys the (already marginal) gross edge by capping winners.

---

## 6. Parameter sensitivity (1h, base model)

Grid over `disp_atr` ∈ {0.3, 0.4, 0.5} × `sweep_lookback` ∈ {10, 15, 20}.

- **ES total return:** −3.3% to −43.0% (best cell: `disp=0.4, lb=10`, PF 0.96).
- **NQ total return:** −49.4% to −79.4% (best cell: `disp=0.5, lb=10`, PF 0.42).

**Finding:** No profitable cell. The best ES cell (PF 0.96) is still net-negative, and the
whole grid is a loss. The result is not a parameter-tuning problem.

---

## 7. Conclusion

**On 1-hour intraday bars, the ICT model is worse than on daily bars, and no variant is
profitable after costs.**

The most important and nuanced result:
1. **ES 1h carries a small, persistent gross edge** (+0.21 to +0.30 R/trade, present in
   both IS and OOS). The ICT concepts have *some* genuine predictive content on 1-hour ES.
2. **The edge is not tradeable:** it is smaller than the transaction cost (~0.37 R/trade),
   driven by tight 1-hour stops that inflate the notional (and thus the cost) per unit of
   risk. Net, ES loses ~19% over 2.4 years.
3. **NQ 1h has no gross edge** and loses ~69% net.
4. **Intraday underperforms daily** for this model because higher trade frequency and
   tighter stops push cost-per-trade above the gross edge.

### Practical implication
The bottleneck on ES is **costs, not signal**. The gross edge (+0.25R) would need to roughly
double — or the cost per trade halved — to be tradeable. Realistic levers (all of which risk
overfitting if chased):
- **Wider stops / lower frequency** to cut cost-per-trade in R terms (fewer, higher-conviction
  setups).
- **Lower execution cost** (limit-order-only entries, tighter spreads, cheaper venue) — the
  model already assumes conservative 4/8 bps round trip.
- A **stronger filter** that raises gross R per trade well above 0.37R.

None of these are present in the tested variants, and none should be claimed as an edge
without out-of-sample proof.

### Caveats
- **2.4 years only** (the max free 1h history). Shorter than the 26-year daily study, so
  the IS/OOS evidence is thinner.
- **Continuous front-month futures** include roll gaps.
- Costs are **conservative** (4 bps ES / 8 bps NQ round trip); a real low-cost execution
  could narrow the ES gap but not close it.

### Bottom line
If the goal is a tradeable intraday strategy, **this ICT model is not it** — the ES gross
edge is real but smaller than its cost, and NQ has no edge. The concepts show a hint of
predictive power on 1h ES, but not enough to deploy mechanically.

---

## Files
- `run_intraday.py` — intraday runner (reuses `ict.py` / `strategy.py` / `engine.py`)
- `results_intraday/` — summary_base.csv, ablations.csv, management.csv, sensitivity.csv,
  validation.csv, trades_*.csv, equity_*.png