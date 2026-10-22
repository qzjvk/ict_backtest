"""
Reverse ICT backtest + randomization test.

Reverse ICT = the same ICT setup (sweep -> displacement -> FVG re-entry) with the
opposite directional bet: every signal is mirrored (side flipped, stop/target
mirrored around the entry reference). ICT bets the sweep was a trap (reversal);
the reverse bets the sweep was real (continuation). Same entry level, same risk and
reward distances, so the RR is unchanged.

This is a directional control: if the ICT reversal bet has genuine predictive
content, reverse ICT should differ from ICT; if the bet is a coin flip, both should
be ~equal (and both lose to costs).

For each timeframe (daily, 1h, 5m) and symbol (ES, NQ):
  - ICT base and reverse ICT base on real data
  - randomization test: R synthetic datasets (bootstrap of the empirical return
    distribution, no temporal structure), run BOTH models -> two null distributions
    -> where do the real ICT and real reverse results sit?

Outputs to results_reverse/:
  summary.csv, randomization.csv,
  compare_<tf>_<sym>.png  (equity: ICT vs reverse vs buy&hold)
  perm_<tf>_<sym>.png     (real vs random null, total return + PF)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data import load
from engine import EngineConfig, performance_stats, run_backtest
from strategy import generate_signals, reverse_signals
from run import make_params

OUT = Path(__file__).parent / "results_reverse"
OUT.mkdir(exist_ok=True)

COST_BPS = {"ES": 4.0, "NQ": 8.0}  # round trip: slippage + commission
TIMEFRAMES = [("daily", "1d"), ("1h", "1h"), ("5m", "5m")]
N_RANDOM = 150
SEED = 20261007


def run_on(df: pd.DataFrame, sym: str, signals, p, engine_over: dict | None = None):
    cfg = dict(cost_bps=COST_BPS[sym])
    if engine_over:
        cfg.update(engine_over)
    curve, trades = run_backtest(df, signals, p, EngineConfig(**cfg))
    stats = performance_stats(curve, trades, df["Close"])
    stats["symbol"] = sym
    return stats, curve, trades


def make_random_data(real: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Synthetic OHLC: bootstrap of empirical log-returns (preserves the return
    distribution incl. fat tails) + wicks sampled from the empirical wick
    distribution. No temporal structure -> null model."""
    n = len(real)
    c = real["Close"].values
    logret = np.diff(np.log(c))
    boot = logret[rng.integers(0, len(logret), size=len(logret))]
    logp = np.empty(n)
    logp[0] = np.log(c[0])
    logp[1:] = np.log(c[0]) + np.cumsum(boot)
    C = np.exp(logp)
    O = np.empty(n)
    O[0] = c[0]
    O[1:] = C[:-1]
    body_hi = np.maximum(real["Open"].values, real["Close"].values)
    body_lo = np.minimum(real["Open"].values, real["Close"].values)
    up_wick = real["High"].values - body_hi
    dn_wick = body_lo - real["Low"].values
    H = np.maximum(O, C) + up_wick[rng.integers(0, len(up_wick), size=n)]
    L = np.minimum(O, C) - dn_wick[rng.integers(0, len(dn_wick), size=n)]
    return pd.DataFrame({"Open": O, "High": H, "Low": L, "Close": C}, index=real.index)


def plot_compare(tf: str, sym: str, df: pd.DataFrame, ict_curve: pd.Series, rev_curve: pd.Series):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(ict_curve.index, ict_curve.values, lw=1.4, color="tab:blue", label="ICT (reversal)")
    ax.plot(rev_curve.index, rev_curve.values, lw=1.4, color="tab:orange", label="Reverse ICT (continuation)")
    bh = df["Close"] / df["Close"].iloc[0] * ict_curve.iloc[0]
    ax.plot(bh.index, bh.values, lw=1.0, alpha=0.6, color="tab:gray", label="Buy & hold")
    ax.set_title(f"{sym} {tf} — ICT vs Reverse ICT (1% risk/trade)")
    ax.set_ylabel("Equity ($, start 100k)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / f"compare_{tf}_{sym}.png", dpi=130)
    plt.close(fig)


def plot_perm(tf, sym, ict_ret, rev_ret, ict_pf, rev_pf,
              r_ict_ret, r_rev_ret, r_ict_pf, r_rev_pf):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax = axes[0]
    ax.hist(r_ict_ret, bins=35, alpha=0.5, color="tab:blue", label="random: ICT")
    ax.hist(r_rev_ret, bins=35, alpha=0.5, color="tab:orange", label="random: reverse")
    ax.axvline(ict_ret, color="tab:blue", lw=2, ls="--", label=f"real ICT: {ict_ret:+.1f}%")
    ax.axvline(rev_ret, color="tab:orange", lw=2, ls="--", label=f"real reverse: {rev_ret:+.1f}%")
    ax.set_title(f"{sym} {tf} — total return: real vs random null")
    ax.set_xlabel("Total return (%)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.hist(np.clip(r_ict_pf, 0, 3), bins=35, alpha=0.5, color="tab:blue", label="random: ICT")
    ax.hist(np.clip(r_rev_pf, 0, 3), bins=35, alpha=0.5, color="tab:orange", label="random: reverse")
    ax.axvline(min(ict_pf, 3), color="tab:blue", lw=2, ls="--", label=f"real ICT: {ict_pf:.2f}")
    ax.axvline(min(rev_pf, 3), color="tab:orange", lw=2, ls="--", label=f"real reverse: {rev_pf:.2f}")
    ax.set_title(f"{sym} {tf} — profit factor: real vs random null")
    ax.set_xlabel("Profit factor")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / f"perm_{tf}_{sym}.png", dpi=130)
    plt.close(fig)


def main():
    rng = np.random.default_rng(SEED)
    p = make_params()

    summary_rows = []
    rand_rows = []

    for tf, interval in TIMEFRAMES:
        for sym in ["ES", "NQ"]:
            df = load(sym, interval=interval)
            print(f"\n===== {sym} {tf}: {len(df)} bars  {df.index[0]} -> {df.index[-1]} =====")

            # ---- real data: ICT vs reverse ----
            ict_sig = generate_signals(df, p)
            rev_sig = reverse_signals(ict_sig)
            ict_stats, ict_curve, ict_trades = run_on(df, sym, ict_sig, p)
            rev_stats, rev_curve, rev_trades = run_on(df, sym, rev_sig, p)

            summary_rows.append({
                "timeframe": tf, "symbol": sym, "model": "ICT",
                "bars": len(df), "trades": ict_stats["trades"],
                "win_rate": ict_stats["win_rate"], "profit_factor": ict_stats["profit_factor"],
                "avg_r_gross": ict_stats["avg_r"], "total_return": ict_stats["total_return"],
                "max_dd": ict_stats["max_dd"], "sharpe": ict_stats["sharpe"],
            })
            summary_rows.append({
                "timeframe": tf, "symbol": sym, "model": "reverse",
                "bars": len(df), "trades": rev_stats["trades"],
                "win_rate": rev_stats["win_rate"], "profit_factor": rev_stats["profit_factor"],
                "avg_r_gross": rev_stats["avg_r"], "total_return": rev_stats["total_return"],
                "max_dd": rev_stats["max_dd"], "sharpe": rev_stats["sharpe"],
            })

            # ---- randomization: both models on R synthetic datasets ----
            r_ict_ret, r_ict_pf, r_ict_r = [], [], []
            r_rev_ret, r_rev_pf, r_rev_r = [], [], []
            for _ in range(N_RANDOM):
                rdf = make_random_data(df, rng)
                rs_ict = generate_signals(rdf, p)
                rs_rev = reverse_signals(rs_ict)
                st_i, _, _ = run_on(rdf, sym, rs_ict, p)
                st_r, _, _ = run_on(rdf, sym, rs_rev, p)
                r_ict_ret.append(st_i["total_return"]); r_ict_pf.append(st_i["profit_factor"]); r_ict_r.append(st_i["avg_r"])
                r_rev_ret.append(st_r["total_return"]); r_rev_pf.append(st_r["profit_factor"]); r_rev_r.append(st_r["avg_r"])

            r_ict_ret = np.array(r_ict_ret); r_ict_pf = np.array(r_ict_pf); r_ict_r = np.array(r_ict_r)
            r_rev_ret = np.array(r_rev_ret); r_rev_pf = np.array(r_rev_pf); r_rev_r = np.array(r_rev_r)

            ict_ret = ict_stats["total_return"]; ict_pf = ict_stats["profit_factor"]; ict_r = ict_stats["avg_r"]
            rev_ret = rev_stats["total_return"]; rev_pf = rev_stats["profit_factor"]; rev_r = rev_stats["avg_r"]

            def pct(arr, x):
                return 100.0 * np.mean(arr <= x)

            def pval(arr, x):
                return (np.sum(arr >= x) + 1) / (len(arr) + 1)

            rand_rows.append({
                "timeframe": tf, "symbol": sym, "model": "ICT",
                "real_return": ict_ret, "real_pf": ict_pf, "real_avg_r": ict_r,
                "rand_mean_return": r_ict_ret.mean(), "rand_median_return": np.median(r_ict_ret),
                "rand_p5_return": np.percentile(r_ict_ret, 5), "rand_p95_return": np.percentile(r_ict_ret, 95),
                "rand_mean_pf": np.nanmean(r_ict_pf), "rand_mean_avg_r": r_ict_r.mean(),
                "real_pctile_return": pct(r_ict_ret, ict_ret), "real_pctile_pf": pct(r_ict_pf, ict_pf),
                "p_value_return": pval(r_ict_ret, ict_ret), "p_value_pf": pval(r_ict_pf, ict_pf),
            })
            rand_rows.append({
                "timeframe": tf, "symbol": sym, "model": "reverse",
                "real_return": rev_ret, "real_pf": rev_pf, "real_avg_r": rev_r,
                "rand_mean_return": r_rev_ret.mean(), "rand_median_return": np.median(r_rev_ret),
                "rand_p5_return": np.percentile(r_rev_ret, 5), "rand_p95_return": np.percentile(r_rev_ret, 95),
                "rand_mean_pf": np.nanmean(r_rev_pf), "rand_mean_avg_r": r_rev_r.mean(),
                "real_pctile_return": pct(r_rev_ret, rev_ret), "real_pctile_pf": pct(r_rev_pf, rev_pf),
                "p_value_return": pval(r_rev_ret, rev_ret), "p_value_pf": pval(r_rev_pf, rev_pf),
            })

            print(f"  ICT     : ret {ict_ret:+7.1f}%  PF {ict_pf:5.2f}  avgR {ict_r:+.3f}  trades {ict_stats['trades']}")
            print(f"  reverse : ret {rev_ret:+7.1f}%  PF {rev_pf:5.2f}  avgR {rev_r:+.3f}  trades {rev_stats['trades']}")
            print(f"  rand ICT    : mean ret {r_ict_ret.mean():+7.1f}%  mean avgR {r_ict_r.mean():+.3f}  "
                  f"[p5 {np.percentile(r_ict_ret,5):+.1f}%, p95 {np.percentile(r_ict_ret,95):+.1f}%]")
            print(f"  rand reverse: mean ret {r_rev_ret.mean():+7.1f}%  mean avgR {r_rev_r.mean():+.3f}  "
                  f"[p5 {np.percentile(r_rev_ret,5):+.1f}%, p95 {np.percentile(r_rev_ret,95):+.1f}%]")
            print(f"  real pctile (return/PF): ICT {pct(r_ict_ret,ict_ret):.0f}/{pct(r_ict_pf,ict_pf):.0f}   "
                  f"reverse {pct(r_rev_ret,rev_ret):.0f}/{pct(r_rev_pf,rev_pf):.0f}")

            plot_compare(tf, sym, df, ict_curve, rev_curve)
            plot_perm(tf, sym, ict_ret, rev_ret, ict_pf, rev_pf,
                      r_ict_ret, r_rev_ret, r_ict_pf, r_rev_pf)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "summary.csv", index=False)
    randdf = pd.DataFrame(rand_rows)
    randdf.to_csv(OUT / "randomization.csv", index=False)

    print("\n\n================ SUMMARY: ICT vs REVERSE ICT (real data) ================")
    print(summary.to_string(index=False))
    print(f"\nOutputs written to {OUT}/")


if __name__ == "__main__":
    main()