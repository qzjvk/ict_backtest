# Reverse ICT Backtest + Randomization Test

**Question:** Does the *opposite* of the ICT setup have an edge? If the ICT
reversal bet (sweep was a trap → fade it) has genuine predictive content, the
reverse bet (sweep was real → continue it) should differ. If the directional bet
is a coin flip, both should land in the same place — and a random-data null shows
whether either is distinguishable from noise.

**Data / method:** identical to the other reports. Real ES/NQ futures (Yahoo
`ES=F`/`NQ=F`), three timeframes (daily 26y, 1h 2.4y, 5m 60d), same ATR-normalized
parameters, 1% risk/trade, conservative same-bar stop-over-target, costs ES 4 bps /
NQ 8 bps round trip. Randomization: 150 synthetic datasets per symbol/timeframe
(bootstrap of the empirical return distribution — preserves volatility + fat tails,
destroys temporal structure), both models run on each → two null distributions.
SEED=20261007.

---

## What "reverse ICT" is

Same setup detection (sweep → displacement → FVG), **opposite directional bet**.
Every signal is mirrored: side flipped, stop and target mirrored around the entry
reference. Risk and reward distances are preserved, so the RR is unchanged.

- **ICT** bets the sweep was a **trap** → reversal. Enters on a retrace into the FVG.
- **Reverse** bets the sweep was **real** → continuation. Enters immediately (price
  is already on the far side of the level after the displacement).

The one structural difference: ICT *waits* for a retrace (may not fill), the reverse
*enters immediately* (almost always fills). So the reverse trades more and is in the
market more often.

---

## Results — real data (ICT vs reverse)

| TF | Sym | Model | Trades | Win% | PF | avg R (gross) | Total return |
|----|-----|-------|-------:|-----:|---:|--------------:|-------------:|
| daily | ES | ICT | 88 | 27.3 | 0.57 | −0.27 | **−25.8%** |
| daily | ES | reverse | 117 | 25.6 | 1.10 | +0.34 | **+11.1%** |
| daily | NQ | ICT | 89 | 21.3 | 0.60 | −0.26 | **−27.6%** |
| daily | NQ | reverse | 112 | 29.5 | 1.02 | +0.29 | **+1.9%** |
| 1h | ES | ICT | 169 | 40.8 | 0.84 | +0.25 | **−18.7%** |
| 1h | ES | reverse | 213 | 22.5 | 0.34 | −0.19 | **−84.2%** |
| 1h | NQ | ICT | 175 | 28.6 | 0.37 | −0.09 | **−69.4%** |
| 1h | NQ | reverse | 219 | 39.3 | 0.13 | +0.10 | **−107.1%** |
| 5m | ES | ICT | 161 | 17.4 | 0.07 | −0.03 | **−95.6%** |
| 5m | ES | reverse | 184 | 19.6 | 0.09 | +0.28 | **−100.0%** |
| 5m | NQ | ICT | 187 | 12.8 | 0.06 | +0.06 | **−98.0%** |
| 5m | NQ | reverse | 246 | 40.7 | 0.02 | +0.03 | **−100.0%** |

On the surface, the **reverse looks better on daily** (+11.1% ES, +1.9% NQ) while ICT
loses. That is the headline the randomization test exists to check.

---

## Randomization test — where does the real result sit?

`pctile` = the real result's percentile within the 150-run random null for the
*same model*. High (→100) = better than random (genuine edge). Low (→0) = worse than
random (harmful). Middle (≈50) = indistinguishable from noise.

| TF | Sym | Model | Real ret | Random mean ret | Random mean avgR | Real pctile (ret / PF) |
|----|-----|-------|---------:|----------------:|-----------------:|:----------------------|
| daily | ES | ICT | −25.8% | −3.7% | +0.03 | **6 / 1** |
| daily | ES | reverse | +11.1% | **+12.2%** | +0.22 | 65 / 67 |
| daily | NQ | ICT | −27.6% | −10.9% | −0.01 | **19 / 13** |
| daily | NQ | reverse | +1.9% | **+16.1%** | +0.29 | 60 / 61 |
| 1h | ES | ICT | −18.7% | −44.5% | +0.03 | **93 / 92** |
| 1h | ES | reverse | −84.2% | −122.5% | +0.05 | 65 / 18 |
| 1h | NQ | ICT | −69.4% | −58.7% | +0.03 | 19 / 5 |
| 1h | NQ | reverse | −107.1% | −101.7% | +0.02 | 10 / 3 |
| 5m | ES | ICT | −95.6% | −96.6% | +0.03 | 79 / 11 |
| 5m | ES | reverse | −100.0% | −100.1% | +0.03 | 91 / 53 |
| 5m | NQ | ICT | −98.0% | −98.1% | +0.04 | 64 / 34 |
| 5m | NQ | reverse | −100.0% | −100.0% | −0.00 | 97 / 11 |

### Reading it

- **Daily — ICT is *worse* than random** (6th / 19th percentile). The reversal bet is
  actively harmful: it loses more than a coin flip would.
- **Daily — reverse is *≈ random** (65th / 60th percentile). Its positive result is
  **not an edge** — the model's random-data baseline is *also* positive (+12.2% ES,
  +16.1% NQ). The real result sits right at the random mean. It is making its
  baseline money, not extracting signal.
- **1h ES — ICT is *better* than random** (93rd percentile). This is the one genuine
  signal in the whole study: the ES 1h gross edge (+0.25R) is real (better than noise),
  but it is smaller than the cost (~0.37R/trade), so it is still net negative (−18.7%).
- **1h NQ — both worse than random.** No edge.
- **5m — degenerate.** Everything is −100% (costs wipe the account in 60 days), so the
  null distribution collapses to a point and the percentiles are meaningless. The 5m
  sample is too short and too cost-dominated to be informative on its own.

---

## Why the reverse model has a positive baseline on random data

This is the crux, so it is worth stating precisely. The reverse model's *random-data*
mean is positive (+12.2% ES / +16.1% NQ daily; pooled mean gross R ≈ **+0.16** across
4,000 random trades). That is a **structural artifact of the model, not a market edge**:

- The mirrored stop/target gives the reverse a **fat-tailed R distribution**. The
  median trade loses exactly **1R** (hits the stop), but a small fraction of trades
  have an extreme planned/realized RR (planned RR median 2.0, p99 11.5, max 22;
  realized RR p99 88, max ~20,000 when the stop is very tight).
- Those rare big winners dominate the mean: the **top 10 trades of 4,008 account for
  ~66% of all gross R**. The mean is therefore high-variance and pushed positive by a
  handful of lucky extreme wins — on *random* data.
- Because the model earns this on noise, a positive result on real data is **not
  evidence of skill**. The randomization test is what separates the two: the real
  reverse result (65th/60th percentile) is inside its own random distribution, i.e.
  exactly what you would get with no edge.

The ICT model does **not** have this artifact — its random-data mean avgR is ≈ 0
(+0.03 ES, −0.01 NQ daily), as a fair model should. That is why the ICT null is a
cleaner "no edge" benchmark, and why ICT's *negative* daily result (worse than random)
is a meaningful statement (the reversal bet is harmful), whereas the reverse's
*positive* daily result is not (it is the model's baseline).

---

## Conclusion

1. **Neither ICT nor reverse ICT has a robust, genuine edge** at any timeframe.
2. **The ICT reversal bet is actively harmful on daily** — it lands in the bottom
   decile of its own random null (worse than a coin flip).
3. **The reverse ICT's positive daily result is a model artifact**, not an edge: the
   same model earns a positive return on pure random data (fat-tailed R distribution),
   and the real result sits at the random mean (65th/60th percentile).
4. **The only genuine signal in the entire study is the small 1h-ES gross edge**
   (ICT, 93rd percentile — better than random). It is real but smaller than its
   transaction cost, so it is net negative (−18.7%).
5. Flipping the direction of a setup does not turn a losing strategy into a winning
   one. On daily it swaps "worse than random" for "≈ random (with a positive baseline
   artifact)"; on 1h/5m both directions lose to costs.

**Bottom line:** the sweep→displacement→FVG setup, in either direction, does not
extract a tradable edge from ES/NQ after costs. The directional bet (reversal vs
continuation) has no reliable predictive content — the one exception (1h-ES gross edge)
is smaller than the cost of trading it.

---

## Files

- `run_reverse.py` — runner (ICT + reverse + 150-run randomization, all timeframes).
- `strategy.py::reverse_signals` — the mirror (flip side, mirror stop/target around entry ref).
- `results_reverse/summary.csv` — real-data ICT vs reverse.
- `results_reverse/randomization.csv` — null distributions + percentiles + p-values.
- `results_reverse/compare_<tf>_<sym>.png` — equity: ICT vs reverse vs buy&hold.
- `results_reverse/perm_<tf>_<sym>.png` — real vs random null (total return + PF).