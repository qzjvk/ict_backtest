"""
Intraday runner: ICT sweep->displacement->FVG backtest on 1-hour ES/NQ bars.

Reuses ict.py / strategy.py / engine.py and the variant definitions from run.py.
The base parameters are ATR-normalized (scale-free), so the same values are used
as in the daily study for a clean comparison.

IS/OOS: the sample is split at its midpoint (first half IS, second half OOS).
Outputs to results_intraday/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data import load
from engine import EngineConfig, performance_stats, run_backtest
from strategy import generate_signals
from run import VARIANTS, MGMT_VARIANTS, make_params

OUT = Path(__file__).parent / "results_intraday"
OUT.mkdir(exist_ok=True)

INTERVAL = "1h"
COST_BPS = {"ES": 4.0, "NQ": 8.0}  # round trip: slippage + commission


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
    return pd.DataFrame([{
        "side": "L" if t.side == 1 else "S",
        "entry_date": t.entry_date, "entry": round(t.entry, 2),
        "stop": round(t.stop, 2), "target": round(t.target, 2),
        "exit_date": t.exit_date, "exit": round(t.exit, 2),
        "pnl": round(t.pnl, 2), "R": round(t.r_multiple, 2),
        "bars": t.bars_held, "reason": t.exit_reason,
        "rr_planned": round(t.rr_planned, 2),
    } for t in trades])


def main():
    data = {s: load(s, interval=INTERVAL) for s in ["ES", "NQ"]}
    for s, d in data.items():
        print(f"{s}: {len(d)} bars  {d.index[0]} -> {d.index[-1]}")

    # midpoint IS/OOS split (by position, no overlap)
    halves = {s: len(d) // 2 for s, d in data.items()}
    for s, h in halves.items():
        print(f"{s} split: IS -> {data[s].index[h-1]}   OOS -> {data[s].index[h]}")

    # ---------------- base model: IS / OOS / all ----------------
    rows = []
    curves = {}
    for sym in ["ES", "NQ"]:
        df = data[sym]
        h = halves[sym]
        for label, sub in [
            ("IS", df.iloc[:h]),
            ("OOS", df.iloc[h:]),
            ("ALL", df),
        ]:
            p = make_params()
            stats, curve, trades = run_on(sub, sym, "base", p)
            stats["period"] = label
            rows.append(stats)
            if label == "ALL":
                curves[(sym, "base")] = curve
                trade_rows(trades).to_csv(OUT / f"trades_{sym}_base.csv", index=False)

    summary = pd.DataFrame(rows)
    cols = ["symbol", "period", "variant", "years", "total_return", "cagr", "sharpe",
            "sortino", "max_dd", "calmar", "trades", "win_rate", "profit_factor",
            "avg_r", "avg_bars_held", "longs", "shorts", "exposure",
            "bh_return", "bh_max_dd", "bh_sharpe"]
    summary = summary[[c for c in cols if c in summary.columns]]
    summary.to_csv(OUT / "summary_base.csv", index=False)
    print("\n=== BASE MODEL (1h) — sweep + displacement + FVG re-entry + min RR ===")
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
    print("\n=== ABLATIONS (1h) ===")
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
    print("\n=== POSITION MANAGEMENT (1h) ===")
    print(mgdf.to_string(index=False))

    # ---------------- sensitivity (base model) ----------------
    import itertools
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
    print("\n=== SENSITIVITY (1h, base model) ===")
    print(sensdf.to_string(index=False))

    # ---------------- IS/OOS validation of variants with positive expectancy ----------------
    all_var = pd.concat([ablation, mgdf], ignore_index=True)
    good = (all_var.groupby("variant")["avg_r"].mean() > 0).index.tolist()
    good = [v for v in good if v != "base"]
    val = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        h = halves[sym]
        for v in good:
            pover = VARIANTS.get(v, {})
            eover = next((e for n, _, e in MGMT_VARIANTS if n == v), None)
            p = make_params(**pover)
            for label, sub in [("IS", df.iloc[:h]), ("OOS", df.iloc[h:])]:
                stats, _, _ = run_on(sub, sym, v, p, engine_over=eover)
                stats["period"] = label
                val.append(stats)
    if val:
        valdf = pd.DataFrame(val)
        valdf = valdf[["symbol", "variant", "period", "total_return", "max_dd",
                       "trades", "win_rate", "profit_factor", "avg_r"]]
        valdf.to_csv(OUT / "validation.csv", index=False)
        print("\n=== IS/OOS VALIDATION (1h, variants with avg_r > 0) ===")
        print(valdf.to_string(index=False))
    else:
        print("\n=== IS/OOS VALIDATION: no variant with positive avg_r ===")

    # ---------------- equity curves ----------------
    for sym in ["ES", "NQ"]:
        fig, ax = plt.subplots(figsize=(11, 5.5))
        c = curves[(sym, "base")]
        ax.plot(c.index, c.values, label="ICT strategy (1% risk/trade)", lw=1.4)
        bh = data[sym]["Close"] / data[sym]["Close"].iloc[0] * c.iloc[0]
        ax.plot(bh.index, bh.values, label="Buy & hold", lw=1.0, alpha=0.7)
        ax.set_title(f"{sym} — ICT sweep/displacement/FVG model, 1h bars")
        ax.set_ylabel("Equity ($, start 100k)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(OUT / f"equity_{sym}_base.png", dpi=130)
        plt.close(fig)
    print(f"\nOutputs written to {OUT}/")


if __name__ == "__main__":
    main()