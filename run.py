"""
Main runner: ICT sweep->displacement->FVG backtest on ES (S&P 500) and NQ (Nasdaq 100).

Outputs (in results/):
  summary_base.csv      - base model, IS / OOS / all, per symbol
  ablations.csv         - which ICT concept contributes
  management.csv        - breakeven / partial profit-taking variants
  validation.csv        - IS/OOS split of variants with positive expectancy
  sensitivity.csv       - parameter sensitivity (base model)
  trades_<SYM>_<variant>.csv
  equity_<SYM>_base.png
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
from strategy import Params, generate_signals

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)

IS_END = "2015-12-31"   # in-sample end
OOS_START = "2016-01-01"

VARIANTS = {
    # base = sweep + displacement + FVG re-entry + min RR
    "base":               {},
    "base+pd":            {"use_pd": True},
    "base+choch":         {"structure": "choch"},
    "base+bos":           {"structure": "bos"},
    "base+trend":         {"use_trend": True},
    "base+break":         {"require_break": True},
    "base+ce":            {"ce_entry": True},
    "base+trend+break":   {"use_trend": True, "require_break": True},
    "no_sweep":           {"require_sweep": False},
    "no_fvg":             {"use_fvg_entry": False},
    "no_sweep_fvg":       {"require_sweep": False, "use_fvg_entry": False},
}

# position-management variants: (name, strategy overrides, engine overrides)
MGMT_VARIANTS = [
    ("base+be1r",           {},            dict(be_at_r=1.0)),
    ("base+partial1r",      {},            dict(partial_r=1.0)),
    ("base+fixed1.5r",      {},            dict(fixed_rr=1.5)),
    ("base+fixed2r",        {},            dict(fixed_rr=2.0)),
    ("base+trend+be1r",     {"use_trend": True},  dict(be_at_r=1.0)),
    ("base+trend+partial1r", {"use_trend": True}, dict(partial_r=1.0)),
    ("base+break+partial1r", {"require_break": True}, dict(partial_r=1.0)),
]

COST_BPS = {"ES": 4.0, "NQ": 8.0}  # round trip: slippage + commission


def make_params(**over) -> Params:
    base = dict(k=2, atr_period=14, disp_atr=0.4, sweep_lookback=15,
                max_wait=5, max_hold=15, min_rr=1.0, stop_buf_atr=0.25,
                structure="any", use_pd=False, use_fvg_entry=True, require_sweep=True)
    base.update(over)
    return Params(**base)


def run_variant(df: pd.DataFrame, sym: str, variant: str, p: Params,
                start: str | None = None, end: str | None = None,
                engine_over: dict | None = None):
    d = df
    if start:
        d = d.loc[start:]
    if end:
        d = d.loc[:end]
    signals = generate_signals(d, p)
    cfg = dict(cost_bps=COST_BPS[sym])
    if engine_over:
        cfg.update(engine_over)
    curve, trades = run_backtest(d, signals, p, EngineConfig(**cfg))
    bench = d["Close"]
    stats = performance_stats(curve, trades, bench)
    stats["symbol"] = sym
    stats["variant"] = variant
    return stats, curve, trades


def main():
    data = {s: load(s) for s in ["ES", "NQ"]}
    for s, d in data.items():
        print(f"{s}: {len(d)} bars  {d.index[0].date()} -> {d.index[-1].date()}")

    # ---------------- base model: IS / OOS / all ----------------
    rows = []
    curves = {}
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for label, start, end in [
            ("IS 2000-2015", None, IS_END),
            ("OOS 2016-2026", OOS_START, None),
            ("ALL 2000-2026", None, None),
        ]:
            p = make_params()
            stats, curve, trades = run_variant(df, sym, "base", p, start, end)
            stats["period"] = label
            rows.append(stats)
            if label.startswith("ALL"):
                curves[(sym, "base")] = curve
                pd.DataFrame([{
                    "side": "L" if t.side == 1 else "S",
                    "entry_date": t.entry_date.date(), "entry": round(t.entry, 2),
                    "stop": round(t.stop, 2), "target": round(t.target, 2),
                    "exit_date": t.exit_date.date(), "exit": round(t.exit, 2),
                    "pnl": round(t.pnl, 2), "R": round(t.r_multiple, 2),
                    "bars": t.bars_held, "reason": t.exit_reason,
                    "rr_planned": round(t.rr_planned, 2),
                } for t in trades]).to_csv(OUT / f"trades_{sym}_base.csv", index=False)

    summary = pd.DataFrame(rows)
    cols = ["symbol", "period", "variant", "years", "total_return", "cagr", "sharpe",
            "sortino", "max_dd", "calmar", "trades", "win_rate", "profit_factor",
            "avg_r", "avg_bars_held", "longs", "shorts", "exposure",
            "bh_return", "bh_max_dd", "bh_sharpe"]
    summary = summary[[c for c in cols if c in summary.columns]]
    summary.to_csv(OUT / "summary_base.csv", index=False)
    print("\n=== BASE MODEL (sweep + displacement + FVG re-entry + min RR) ===")
    print(summary.to_string(index=False))

    # ---------------- ablations (full period) ----------------
    ab = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for name, over in VARIANTS.items():
            p = make_params(**over)
            stats, curve, trades = run_variant(df, sym, name, p)
            ab.append(stats)
            if name == "base":
                continue
            pd.DataFrame([{
                "side": "L" if t.side == 1 else "S",
                "entry_date": t.entry_date.date(), "entry": round(t.entry, 2),
                "stop": round(t.stop, 2), "target": round(t.target, 2),
                "exit_date": t.exit_date.date(), "exit": round(t.exit, 2),
                "pnl": round(t.pnl, 2), "R": round(t.r_multiple, 2),
                "bars": t.bars_held, "reason": t.exit_reason,
            } for t in trades]).to_csv(OUT / f"trades_{sym}_{name}.csv", index=False)
    ablation = pd.DataFrame(ab)
    ablation = ablation[["symbol", "variant", "total_return", "cagr", "sharpe", "max_dd",
                         "trades", "win_rate", "profit_factor", "avg_r", "exposure"]]
    ablation.to_csv(OUT / "ablations.csv", index=False)
    print("\n=== ABLATIONS (which ICT concept contributes) ===")
    print(ablation.to_string(index=False))

    # ---------------- position management variants (full period) ----------------
    mg = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for name, pover, eover in MGMT_VARIANTS:
            p = make_params(**pover)
            stats, _, trades = run_variant(df, sym, name, p, engine_over=eover)
            mg.append(stats)
            pd.DataFrame([{
                "side": "L" if t.side == 1 else "S",
                "entry_date": t.entry_date.date(), "entry": round(t.entry, 2),
                "stop": round(t.stop, 2), "target": round(t.target, 2),
                "exit_date": t.exit_date.date(), "exit": round(t.exit, 2),
                "pnl": round(t.pnl, 2), "R": round(t.r_multiple, 2),
                "bars": t.bars_held, "reason": t.exit_reason,
            } for t in trades]).to_csv(OUT / f"trades_{sym}_{name}.csv", index=False)
    mgdf = pd.DataFrame(mg)
    mgdf = mgdf[["symbol", "variant", "total_return", "cagr", "sharpe", "max_dd",
                 "trades", "win_rate", "profit_factor", "avg_r", "exposure"]]
    mgdf.to_csv(OUT / "management.csv", index=False)
    print("\n=== POSITION MANAGEMENT (breakeven / partial at 1R) ===")
    print(mgdf.to_string(index=False))

    # ---------------- IS/OOS validation of variants with positive expectancy ----------------
    all_var = pd.concat([ablation, mgdf], ignore_index=True)
    good = (all_var.groupby("variant")["avg_r"].mean() > 0).index.tolist()
    good = [v for v in good if v != "base"]
    val = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for v in good:
            pover = VARIANTS.get(v, {})
            eover = next((e for n, _, e in MGMT_VARIANTS if n == v), None)
            p = make_params(**pover)
            for label, start, end in [
                ("IS 2000-2015", None, IS_END),
                ("OOS 2016-2026", OOS_START, None),
            ]:
                stats, _, _ = run_variant(df, sym, v, p, start, end, eover)
                stats["period"] = label
                val.append(stats)
    if val:
        valdf = pd.DataFrame(val)
        valdf = valdf[["symbol", "variant", "period", "total_return", "max_dd",
                       "trades", "win_rate", "profit_factor", "avg_r"]]
        valdf.to_csv(OUT / "validation.csv", index=False)
        print("\n=== IS/OOS VALIDATION (variants with avg_r > 0) ===")
        print(valdf.to_string(index=False))
    else:
        print("\n=== IS/OOS VALIDATION: no variant with positive avg_r ===")

    # ---------------- sensitivity (base model) ----------------
    sens = []
    for sym in ["ES", "NQ"]:
        df = data[sym]
        for disp, lb in itertools.product([0.3, 0.4, 0.5], [10, 15, 20]):
            p = make_params(disp_atr=disp, sweep_lookback=lb)
            stats, _, _ = run_variant(df, sym, "sens", p)
            stats["disp_atr"] = disp
            stats["sweep_lb"] = lb
            sens.append(stats)
    sensdf = pd.DataFrame(sens)[["symbol", "disp_atr", "sweep_lb", "total_return", "cagr",
                                 "sharpe", "max_dd", "trades", "win_rate", "profit_factor"]]
    sensdf.to_csv(OUT / "sensitivity.csv", index=False)
    print("\n=== SENSITIVITY (base model) ===")
    print(sensdf.to_string(index=False))

    # ---------------- equity curves ----------------
    for sym in ["ES", "NQ"]:
        fig, ax = plt.subplots(figsize=(11, 5.5))
        c = curves[(sym, "base")]
        ax.plot(c.index, c.values, label="ICT strategy (1% risk/trade)", lw=1.4)
        bh = data[sym]["Close"] / data[sym]["Close"].iloc[0] * c.iloc[0]
        ax.plot(bh.index, bh.values, label="Buy & hold", lw=1.0, alpha=0.7)
        ax.set_title(f"{sym} — ICT sweep/displacement/FVG model, 2000–2026")
        ax.set_ylabel("Equity ($, start 100k)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(OUT / f"equity_{sym}_base.png", dpi=130)
        plt.close(fig)
    print(f"\nOutputs written to {OUT}/")


if __name__ == "__main__":
    main()