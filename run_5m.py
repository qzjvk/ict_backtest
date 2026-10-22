"""
5-minute runner: ICT sweep->displacement->FVG backtest on 5m ES/NQ bars
(~60 days, the max free 5m history from Yahoo), plus a randomization test.

Randomization test
------------------
To ask "is this strategy's performance distinguishable from noise?", we generate
M synthetic OHLC series that share the real data's return distribution (bootstrap
of empirical 5m log-returns, so fat tails and volatility are preserved) but have
no temporal structure, synthesize realistic wicks from the empirical wick
distribution, and run the identical strategy on each. The real-data result is
then located inside the null distribution (percentile + p-value).

Outputs (in results_5m/):
  summary_base.csv, ablations.csv, management.csv, sensitivity.csv,
  randomization.csv, trades_*.csv,
  equity_*.png, perm_hist_*.png, perm_fan_*.png, price_trades_*.png
"""
from __future__ import annotations

import itertools
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data import load
from engine import EngineConfig, performance_stats, run_backtest
from strategy import generate_signals
from run import VARIANTS, MGMT_VARIANTS, make_params

OUT = Path(__file__).parent / "results_5m"
OUT.mkdir(exist_ok=True)

INTERVAL = "5m"
COST_BPS = {"ES": 4.0, "NQ": 8.0}  # round trip: slippage + commission
N_RANDOM = 300          # synthetic datasets per symbol
FAN_CURVES = 40         # random equity curves drawn on the fan plot
SEED = 20261007


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def run_on(df: pd.DataFrame, sym: str, variant: str, p, engine_over: dict | None = None):
    signals = generate_signals(df, p)
    cfg = dict(cost_bps=COST_BPS[sym])
    if engine_over:
        cfg.update(engine_over)
    curve, trades = run_backtest(df, signals, p, EngineConfig(**cfg))
    stats = performance_stats(curve, trades, df["Close"])
    stats["symbol"] = sym
    stats["variant"] = variant
    return stats, curve, trades


def trade_rows(trades) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "side": "L" if t.side == 1 else "S",
            "entry_date": t.entry_date, "entry": round(t.entry, 2),
            "stop": round(t.stop, 2), "target": round(t.target, 2),
            "exit_date": t.exit_date, "exit": round(t.exit, 2),
            "pnl": round(t.pnl, 2), "R": round(t.r_multiple, 2),
            "bars": t.bars_held, "reason": t.exit_reason,
            "rr_planned": round(t.rr_planned, 2),
        }
        for t in trades
    ])


def make_random_data(real: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Synthetic OHLC series: bootstrap of empirical log-returns (preserves the
    return distribution incl. fat tails) + wicks sampled from the empirical
    wick distribution. No temporal structure -> null model."""
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


# --------------------------------------------------------------------------- #
# plots
# --------------------------------------------------------------------------- #
def plot_equity(sym: str, df: pd.DataFrame, curve: pd.Series):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(curve.index, curve.values, label="ICT strategy (1% risk/trade)", lw=1.4, color="tab:blue")
    bh = df["Close"] / df["Close"].iloc[0] * curve.iloc[0]
    ax.plot(bh.index, bh.values, label="Buy & hold", lw=1.0, alpha=0.7, color="tab:gray")
    ax.set_title(f"{sym} — ICT sweep/displacement/FVG model, 5m bars (~60 days)")
    ax.set_ylabel("Equity ($, start 100k)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / f"equity_{sym}_base.png", dpi=130)
    plt.close(fig)


def plot_perm_hist(sym: str, real_ret: float, real_pf: float, rand_ret: np.ndarray, rand_pf: np.ndarray):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.hist(rand_ret, bins=40, color="tab:gray", alpha=0.75, edgecolor="white")
    ax.axvline(real_ret, color="tab:red", lw=2, label=f"real: {real_ret:+.1f}%")
    ax.set_title(f"{sym} — total return: real vs {len(rand_ret)} random datasets")
    ax.set_xlabel("Total return (%)")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    pf_clip = np.clip(rand_pf, 0, 3)
    ax.hist(pf_clip, bins=40, color="tab:gray", alpha=0.75, edgecolor="white")
    ax.axvline(min(real_pf, 3), color="tab:red", lw=2, label=f"real: {real_pf:.2f}")
    ax.set_title(f"{sym} — profit factor: real vs random")
    ax.set_xlabel("Profit factor")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / f"perm_hist_{sym}.png", dpi=130)
    plt.close(fig)


def plot_perm_fan(sym: str, df: pd.DataFrame, real_curve: pd.Series, fan_curves: list[pd.Series]):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for c in fan_curves:
        ax.plot(c.index, c.values, lw=0.5, alpha=0.25, color="tab:gray")
    ax.plot(real_curve.index, real_curve.values, lw=1.8, color="tab:red", label="real data")
    ax.axhline(100_000, color="black", lw=0.6, ls="--", alpha=0.5)
    ax.set_title(f"{sym} — equity: real (red) vs {len(fan_curves)} random datasets (gray)")
    ax.set_ylabel("Equity ($, start 100k)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / f"perm_fan_{sym}.png", dpi=130)
    plt.close(fig)


def plot_price_trades(sym: str, df: pd.DataFrame, trades):
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(df.index, df["Close"], lw=0.6, color="tab:gray", label="close")
    for t in trades:
        col = "tab:green" if t.side == 1 else "tab:red"
        ax.scatter(t.entry_date, t.entry, marker="^" if t.side == 1 else "v",
                   s=45, color=col, zorder=3,
                   label="long entry" if t.side == 1 else "short entry")
        ax.scatter(t.exit_date, t.exit, marker="x", s=25, color="black", zorder=3, label="exit")
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(handles=by_label.values(), labels=by_label.keys(), loc="upper left", fontsize=8)
    ax.set_title(f"{sym} — 5m price with ICT base-model trades (entry/exit markers)")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / f"price_trades_{sym}.png", dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    data = {s: load(s, interval=INTERVAL) for s in ["ES", "NQ"]}
    for s, d in data.items():
        print(f"{s}: {len(d)} bars  {d.index[0]} -> {d.index[-1]}")

    halves = {s: len(d) // 2 for s, d in data.items()}
    for s, h in halves.items():
        print(f"{s} split: IS -> {data[s].index[h-1]}   OOS -> {data[s].index[h]}")

    # ---------------- base model: IS / OOS / all ----------------
    rows = []
    curves = {}
    base_trades = {}
    for sym in ["ES", "NQ"]:
        df = data[sym]
        h = halves[sym]
        for label, sub in [("IS", df.iloc[:h]), ("OOS", df.iloc[h:]), ("ALL", df)]:
            p = make_params()
            stats, curve, trades = run_on(sub, sym, "base", p)
            stats["period"] = label
            rows.append(stats)
            if label == "ALL":
                curves[sym] = curve
                base_trades[sym] = trades
                trade_rows(trades).to_csv(OUT / f"trades_{sym}_base.csv", index=False)

    summary = pd.DataFrame(rows)
    cols = ["symbol", "period", "variant", "years", "total_return", "cagr", "sharpe",
            "sortino", "max_dd", "calmar", "trades", "win_rate", "profit_factor",
            "avg_r", "avg_bars_held", "longs", "shorts", "exposure",
            "bh_return", "bh_max_dd", "bh_sharpe"]
    summary = summary[[c for c in cols if c in summary.columns]]
    summary.to_csv(OUT / "summary_base.csv", index=False)
    print("\n=== BASE MODEL (5m) — sweep + displacement + FVG re-entry + min RR ===")
    print(summary.to_string(index=False))

    # ---------------- ablations (full period) ----------------
    ab = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for name, over in VARIANTS.items():
            p = make_params(**over)
            stats, _, trades = run_on(df, sym, name, p)
            ab.append(stats)
            if name != "base":
                trade_rows(trades).to_csv(OUT / f"trades_{sym}_{name}.csv", index=False)
    ablation = pd.DataFrame(ab)
    ablation = ablation[["symbol", "variant", "total_return", "cagr", "sharpe", "max_dd",
                         "trades", "win_rate", "profit_factor", "avg_r", "exposure"]]
    ablation.to_csv(OUT / "ablations.csv", index=False)
    print("\n=== ABLATIONS (5m) ===")
    print(ablation.to_string(index=False))

    # ---------------- position management variants (full period) ----------------
    mg = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for name, pover, eover in MGMT_VARIANTS:
            p = make_params(**pover)
            stats, _, trades = run_on(df, sym, name, p, engine_over=eover)
            mg.append(stats)
            trade_rows(trades).to_csv(OUT / f"trades_{sym}_{name}.csv", index=False)
    mgdf = pd.DataFrame(mg)
    mgdf = mgdf[["symbol", "variant", "total_return", "cagr", "sharpe", "max_dd",
                 "trades", "win_rate", "profit_factor", "avg_r", "exposure"]]
    mgdf.to_csv(OUT / "management.csv", index=False)
    print("\n=== POSITION MANAGEMENT (5m) ===")
    print(mgdf.to_string(index=False))

    # ---------------- sensitivity (base model) ----------------
    sens = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for disp, lb in itertools.product([0.3, 0.4, 0.5], [10, 15, 20]):
            p = make_params(disp_atr=disp, sweep_lookback=lb)
            stats, _, _ = run_on(df, sym, "sens", p)
            stats["disp_atr"] = disp
            stats["sweep_lb"] = lb
            sens.append(stats)
    sensdf = pd.DataFrame(sens)[["symbol", "disp_atr", "sweep_lb", "total_return", "cagr",
                                 "sharpe", "max_dd", "trades", "win_rate", "profit_factor"]]
    sensdf.to_csv(OUT / "sensitivity.csv", index=False)
    print("\n=== SENSITIVITY (5m, base model) ===")
    print(sensdf.to_string(index=False))

    # ---------------- randomization test (base model) ----------------
    rng = np.random.default_rng(SEED)
    rand_rows = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        p = make_params()
        real_stats, real_curve, _ = run_on(df, sym, "base", p)
        rets, pfs, rrs, sharpes, fans = [], [], [], [], []
        for i in range(N_RANDOM):
            rdf = make_random_data(df, rng)
            st, crv, _ = run_on(rdf, sym, "base", p)
            rets.append(st["total_return"])
            pfs.append(st["profit_factor"])
            rrs.append(st["avg_r"])
            sharpes.append(st["sharpe"])
            if i < FAN_CURVES:
                fans.append(crv)
        rets = np.array(rets)
        pfs = np.array(pfs)
        rrs = np.array(rrs)
        sharpes = np.array(sharpes)
        real_ret = real_stats["total_return"]
        real_pf = real_stats["profit_factor"]
        real_r = real_stats["avg_r"]
        real_sh = real_stats["sharpe"]
        # p-values: fraction of random runs at least as good as real (upper tail)
        p_ret = (np.sum(rets >= real_ret) + 1) / (N_RANDOM + 1)
        p_pf = (np.sum(pfs >= real_pf) + 1) / (N_RANDOM + 1)
        pct_ret = 100.0 * np.mean(rets <= real_ret)
        pct_pf = 100.0 * np.mean(pfs <= real_pf)
        rand_rows.append({
            "symbol": sym,
            "real_total_return": real_ret, "real_pf": real_pf,
            "real_avg_r": real_r, "real_sharpe": real_sh,
            "rand_mean_return": rets.mean(), "rand_median_return": np.median(rets),
            "rand_p5_return": np.percentile(rets, 5), "rand_p95_return": np.percentile(rets, 95),
            "rand_mean_pf": np.nanmean(pfs), "rand_median_pf": np.nanmedian(pfs),
            "rand_mean_avg_r": rrs.mean(),
            "real_pctile_return": pct_ret, "real_pctile_pf": pct_pf,
            "p_value_return": p_ret, "p_value_pf": p_pf,
        })
        print(f"\n=== RANDOMIZATION {sym} (base model, {N_RANDOM} random datasets) ===")
        print(f"  real: ret {real_ret:+.1f}%  PF {real_pf:.2f}  avgR {real_r:+.3f}  sharpe {real_sh:.2f}")
        print(f"  random: mean ret {rets.mean():+.1f}%  median {np.median(rets):+.1f}%  "
              f"[p5 {np.percentile(rets,5):+.1f}% , p95 {np.percentile(rets,95):+.1f}%]")
        print(f"  random: mean PF {np.nanmean(pfs):.2f}  median {np.nanmedian(pfs):.2f}  "
              f"mean avgR {rrs.mean():+.3f}")
        print(f"  real percentile: return {pct_ret:.0f}%  PF {pct_pf:.0f}%   "
              f"(p-value return {p_ret:.3f}, PF {p_pf:.3f})")
        plot_perm_hist(sym, real_ret, real_pf, rets, pfs)
        plot_perm_fan(sym, df, real_curve, fans)

    randdf = pd.DataFrame(rand_rows)
    randdf.to_csv(OUT / "randomization.csv", index=False)

    # ---------------- equity + price/trade plots ----------------
    for sym in ["ES", "NQ"]:
        plot_equity(sym, data[sym], curves[sym])
        plot_price_trades(sym, data[sym], base_trades[sym])

    print(f"\nOutputs written to {OUT}/")


if __name__ == "__main__":
    main()