# ICT Concepts Backtest — S&P 500 (ES) & Nasdaq 100 (NQ)

**Date:** 2026-10-06
**Data:** Yahoo Finance continuous front-month futures `ES=F` / `NQ=F`, daily bars,
2000-09-18 → 2026-10-06 (6,577 bars each).
**Split:** In-sample (IS) 2000-01-01 → 2015-12-31 · Out-of-sample (OOS) 2016-01-01 → 2026-10-06.

---

## 1. What was tested

A mechanical, rule-based implementation of the core **Inner Circle Trader (ICT)**
playbook, expressed as a single strategy:

> **Liquidity sweep → Displacement → Fair Value Gap (FVG) re-entry**

**Long setup** (signal at the close of bar *t*; mirrored for shorts):
1. **Liquidity sweep** — within the last `sweep_lookback` bars, price wicked below the
   last confirmed swing low and closed back above it (a "stop hunt").
2. **Displacement** — bar *t−1* is a strong bullish candle (body ≥ `disp_atr` × ATR).
3. **FVG** — the displacement leaves a 3-candle bullish FVG, confirmed by bar *t*.
4. **Entry** — limit order at the FVG edge (fill at the open if a bar opens inside the zone).
5. **Stop** — beyond the sweep extreme (+ ATR buffer).
6. **Target** — the last confirmed swing high (the opposing liquidity pool).
7. **Filters** — minimum reward:risk (RR ≥ 1.0); optional premium/discount, market-structure
   (CHoCH/BOS), trend-alignment, and structure-break filters.

**Execution model (deliberately conservative):**
- Signals at the close of bar *t*; entry order live from *t+1* for at most `max_wait` bars.
- Same-bar ambiguity (stop and target both touched) resolves to the **stop**.
- One position at a time, no pyramiding.
- Position size: fixed fractional risk, **1% of equity per trade**.
- Costs: round-trip bps of notional — ES 4 bps, NQ 8 bps (slippage + commission).

**Base parameters:** `k=2, atr_period=14, disp_atr=0.4, sweep_lookback=15, max_wait=5,
max_hold=15, min_rr=1.0, stop_buf_atr=0.25`.

---

## 2. Base model results

| Symbol | Period | Trades | Win % | Profit Factor | Avg R | Max DD | Exposure |
|--------|--------|-------:|------:|--------------:|------:|-------:|---------:|
| ES | IS 2000–2015 | 57 | 33.3 | 0.68 | −0.16 | −4.2% | 8.1% |
| ES | OOS 2016–2026 | 31 | 19.4 | 0.40 | −0.43 | −5.0% | 4.1% |
| **ES** | **ALL 2000–2026** | **88** | **27.3** | **0.57** | **−0.27** | **−4.4%** | **6.5%** |
| NQ | IS 2000–2015 | 56 | 23.2 | 0.70 | −0.16 | −9.5% | 7.9% |
| NQ | OOS 2016–2026 | 33 | 18.2 | 0.41 | −0.43 | −4.5% | 6.9% |
| **NQ** | **ALL 2000–2026** | **89** | **21.3** | **0.60** | **−0.26** | **−9.5%** | **7.5%** |

**Buy & hold benchmark (same period):** ES +436.8% (max DD −57.1%, Sharpe 0.43) ·
NQ +762.0% (max DD −79.0%, Sharpe 0.45).

**The base model loses money in both samples, on both symbols.** The win rate
(~21–27%) is far too low for the ~2.3R planned reward:risk, and ~70% of trades end at the
stop. The small max drawdown (−4 to −9%) is only because the strategy is in the market
~6–8% of the time — it is not a risk feature, it is a lack of activity.

---

## 3. Ablations — which ICT concept contributes?

Full period, base parameters. Profit factor (PF) and average R-multiple.

| Symbol | Variant | Trades | Win % | PF | Avg R | Max DD |
|--------|---------|-------:|------:|---:|------:|-------:|
| ES | base (sweep+disp+FVG) | 88 | 27.3 | 0.57 | −0.27 | −4.4% |
| ES | + premium/discount | 84 | 27.4 | 0.58 | −0.26 | −4.4% |
| ES | + CHoCH only | 0 | — | — | — | — |
| ES | + BOS only | 0 | — | — | — | — |
| ES | + trend alignment | 9 | 22.2 | 0.30 | −0.50 | −2.0% |
| ES | + structure break | 0 | — | — | — | — |
| ES | + CE (FVG midpoint) entry | 110 | 26.4 | 0.48 | −0.33 | −3.8% |
| ES | **no sweep** | 207 | 32.9 | **1.08** | **+0.23** | **−40.1%** |
| ES | no FVG (next-open entry) | 288 | 36.8 | 0.71 | −0.03 | −8.4% |
| ES | no sweep, no FVG | 477 | 37.7 | 0.74 | −0.02 | −7.9% |
| NQ | base | 89 | 21.3 | 0.60 | −0.26 | −9.5% |
| NQ | + premium/discount | 85 | 22.4 | 0.61 | −0.24 | −9.5% |
| NQ | + trend alignment | 8 | 37.5 | 0.68 | −0.15 | −2.5% |
| NQ | + CE entry | 110 | 28.2 | 0.74 | −0.10 | −11.3% |
| NQ | **no sweep** | 200 | 34.0 | **0.87** | **+0.02** | **−9.7%** |
| NQ | no FVG | 257 | 33.1 | 0.66 | −0.11 | −12.6% |
| NQ | no sweep, no FVG | 457 | 32.8 | 0.61 | −0.14 | −11.7% |

**Findings:**
- **The liquidity-sweep prerequisite is the weakest link.** Removing it (`no_sweep`) is the
  only variant with a positive average R on either symbol. The "sweep → displacement"
  sequence does not add predictive value on daily bars.
- **The CHoCH / BOS / structure-break filters produce zero trades** — they are too strict
  to combine with the sweep + FVG + RR requirements. (Requiring the displacement to break
  structure is also structurally incompatible with the target: once the displacement closes
  beyond the swing, that swing — the target — is already behind the entry, so the RR filter
  rejects everything.)
- **No added filter improves the base model.** Premium/discount, trend alignment, and CE
  entry all leave it losing.

---

## 4. Position-management variants

Breakeven-at-1R, partial (50%) at 1R, and fixed-R targets, full period.

| Symbol | Variant | Trades | Win % | PF | Avg R |
|--------|---------|-------:|------:|---:|------:|
| ES | base | 88 | 27.3 | 0.57 | −0.27 |
| ES | breakeven @ 1R | 89 | 20.2 | 0.47 | −0.26 |
| ES | partial 50% @ 1R | 89 | 43.8 | 0.56 | −0.19 |
| ES | fixed 1.5R target | 90 | 30.0 | 0.56 | −0.26 |
| ES | fixed 2R target | 88 | 26.1 | 0.56 | −0.28 |
| NQ | base | 89 | 21.3 | 0.60 | −0.26 |
| NQ | breakeven @ 1R | 91 | 8.8 | 0.20 | −0.43 |
| NQ | partial 50% @ 1R | 91 | 45.1 | 0.41 | −0.27 |
| NQ | fixed 1.5R target | 89 | 28.1 | 0.51 | −0.28 |
| NQ | fixed 2R target | 89 | 23.6 | 0.52 | −0.30 |

**Finding:** No exit-management change rescues the model. Breakeven-at-1R actually *hurts*
(it converts would-be winners into 0R exits before the far swing target is reached).
Partial profit-taking raises the win rate but not the expectancy.

---

## 5. Parameter sensitivity

Base model, grid over `disp_atr` ∈ {0.3, 0.4, 0.5} × `sweep_lookback` ∈ {10, 15, 20}.

- **ES profit factor:** 0.51 – 0.70 across all 9 cells.
- **NQ profit factor:** 0.58 – 0.64 across all 9 cells.

**Finding:** The result is flat across the whole parameter space. There is no profitable
region to find — the loss is not an artifact of a bad parameter choice.

---

## 6. IS / OOS validation

Every variant with a positive average R over the full period was re-tested on the IS and
OOS halves. A real edge must be present in **both**.

| Symbol | Variant | IS PF (Avg R) | OOS PF (Avg R) | Consistent? |
|--------|---------|--------------|---------------|:-----------:|
| ES | no_sweep | 1.43 (+0.51) | 0.59 (−0.22) | ❌ |
| ES | no_fvg | 0.78 (+0.04) | 0.57 (−0.12) | ❌ |
| ES | no_sweep_fvg | 0.77 (+0.01) | 0.66 (−0.06) | ❌ |
| ES | fixed 1.5R | 0.73 (−0.11) | 0.31 (−0.52) | ❌ |
| NQ | no_sweep | 0.84 (−0.01) | 0.93 (+0.07) | ❌ (≈ breakeven) |
| NQ | no_fvg | 0.65 (−0.13) | 0.71 (−0.07) | ❌ |
| NQ | no_sweep_fvg | 0.62 (−0.13) | 0.59 (−0.15) | ❌ |
| NQ | trend alignment | 1.73 (+0.36, 5 trades) | 0.00 (−1.00, 3 trades) | ❌ |

**Finding:** The one variant that is clearly positive in-sample (ES `no_sweep`, PF 1.43)
**collapses out-of-sample** (PF 0.59). No variant is positive in both halves. This is the
signature of noise, not edge.

---

## 7. Conclusion

**A mechanical ICT "sweep → displacement → FVG re-entry" model has no robust edge on
daily-bar ES and NQ over 2000–2026.** It loses money in-sample and out-of-sample, on both
symbols, across every filter, exit-management rule, and parameter combination tested.

The most informative results:
1. **The liquidity-sweep filter is the weakest component** — dropping it is the only change
   that produces positive expectancy, and even that does not survive the IS/OOS split.
2. **The core problem is the win rate.** The FVG re-entry with a stop beyond the sweep
   extreme yields a ~21–27% win rate against a ~2.3R target that is reached only ~22% of
   the time. Expectancy is negative after costs.
3. **The result is parameter-insensitive** — this is not a tuning problem.

### Why this is an honest (if disappointing) result
- ICT/SMC concepts are largely **repackaged classical technical analysis** (support/
  resistance, momentum, mean reversion). On liquid index futures at the daily timeframe,
  those patterns do not contain a persistent, cost-adjusted edge.
- The concepts are **visually intuitive but not sufficiently predictive** to overcome
  slippage and commissions when traded mechanically.
- This tests the **mechanical rule-based** version of the playbook. Discretionary ICT
  traders add context (news, session timing, higher-timeframe bias, confluence) that is not
  captured here.

### Caveats / limitations
- **Daily bars only.** ICT concepts are most often applied on intraday timeframes
  (1/5/15-min), where any edge is more likely to live. 26 years of intraday ES/NQ data is
  not readily available, so this could not be tested.
- **Continuous front-month futures** (`ES=F`/`NQ=F`) include roll gaps that add noise.
- The model is **conservative** (same-bar stop priority, limit fills, explicit costs), so
  real results would not be better than shown.

### Bottom line
If the goal is a standalone, mechanical daily-bar strategy, **do not deploy this model** —
it has no edge. If the goal is to understand whether ICT concepts are exploitable, the
evidence here is that **they are not, at the daily timeframe, in a rule-based form.**

---

## Files
- `ict.py` — concept detection (swings, structure, sweeps, FVG, order blocks, P/D, ATR)
- `strategy.py` — signal generation (`Params`, `generate_signals`)
- `engine.py` — backtest engine + performance stats
- `data.py` — data loader (CSV-cached)
- `run.py` — runner (base, ablations, management, sensitivity, IS/OOS validation)
- `results/` — all CSVs and equity plots