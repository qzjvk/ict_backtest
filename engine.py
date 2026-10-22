"""
Backtest engine: executes signals on daily bars with conservative assumptions.

Execution model
  - Signals are generated at the close of bar t; the entry order is live from
    bar t+1 for at most `max_wait` bars.
  - FVG entry: limit at the FVG edge. If a bar opens inside the zone, fill at
    the open. If the bar gaps through the stop before/without a fill, the
    order is cancelled (no fill).
  - Same-bar ambiguity (stop and target both touched) resolves to the stop
    (conservative).
  - One position at a time, no pyramiding.
  - Position size: fixed fractional risk (default 1% of equity per trade).
  - Costs: round-trip bps of notional (slippage + commission).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy import Params, Signal


@dataclass
class Trade:
    side: int
    entry_date: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_date: pd.Timestamp
    exit: float
    units: float
    pnl: float
    r_multiple: float
    bars_held: int
    exit_reason: str
    rr_planned: float


@dataclass
class EngineConfig:
    initial_equity: float = 100_000.0
    risk_pct: float = 0.01
    cost_bps: float = 4.0  # round trip, bps of notional
    be_at_r: float = 0.0   # >0: move stop to breakeven once price reaches this many R
    partial_r: float = 0.0 # >0: close 50% at this many R and move stop to breakeven
    fixed_rr: float = 0.0  # >0: exit at a fixed R multiple instead of the swing target


def run_backtest(df: pd.DataFrame, signals: list[Signal], p: Params, cfg: EngineConfig) -> tuple[pd.DataFrame, list[Trade]]:
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    idx = df.index
    n = len(df)

    equity = cfg.initial_equity
    equity_curve = np.full(n, np.nan)
    trades: list[Trade] = []
    eq_trades: list[tuple] = []  # (fill_bar, exit_bar, units, fill_px, side, pnl)
    busy_until = -1  # last bar index the current position occupies

    for sig in signals:
        t = sig.t
        if t <= busy_until:
            continue  # already in a position
        if t + 1 >= n:
            continue

        # ---- find the fill ----
        fill_bar = -1
        fill_px = np.nan
        for u in range(t + 1, min(t + 1 + p.max_wait, n)):
            if sig.side == 1:
                if o[u] <= sig.stop:
                    break  # gapped through the stop: order cancelled
                if np.isnan(sig.entry_ref):
                    fill_bar = u
                    fill_px = o[u]
                    break
                if l[u] <= sig.entry_ref:
                    fill_bar = u
                    fill_px = min(o[u], sig.entry_ref)
                    break
            else:
                if o[u] >= sig.stop:
                    break
                if np.isnan(sig.entry_ref):
                    fill_bar = u
                    fill_px = o[u]
                    break
                if h[u] >= sig.entry_ref:
                    fill_bar = u
                    fill_px = max(o[u], sig.entry_ref)
                    break
        if fill_bar < 0:
            continue

        # ---- sizing ----
        risk_per_unit = abs(fill_px - sig.stop)
        if risk_per_unit <= 0:
            continue
        units = (equity * cfg.risk_pct) / risk_per_unit
        target = sig.target
        if cfg.fixed_rr > 0:
            target = fill_px + cfg.fixed_rr * risk_per_unit * sig.side

        # ---- manage the position ----
        cur_stop = sig.stop
        remaining = units
        partial_pnl = 0.0
        partial_done = False
        be_done = False

        exit_bar = -1
        exit_px = np.nan
        reason = ""
        for u in range(fill_bar, n):
            bars_held = u - fill_bar
            if sig.side == 1:
                if l[u] <= cur_stop:
                    exit_bar, exit_px, reason = u, cur_stop, "stop"
                    break
                # breakeven / partial triggers (checked after the stop: conservative)
                if not be_done and cfg.be_at_r > 0 and h[u] >= fill_px + cfg.be_at_r * risk_per_unit:
                    cur_stop = fill_px
                    be_done = True
                if not partial_done and cfg.partial_r > 0 and h[u] >= fill_px + cfg.partial_r * risk_per_unit:
                    trig = fill_px + cfg.partial_r * risk_per_unit
                    partial_pnl = remaining * 0.5 * (trig - fill_px) * sig.side
                    remaining *= 0.5
                    cur_stop = max(cur_stop, fill_px)
                    partial_done = True
                # stop just raised to breakeven and the bar also trades through it
                if cur_stop > sig.stop and l[u] <= cur_stop:
                    exit_bar, exit_px, reason = u, cur_stop, "stop"
                    break
                if h[u] >= target:
                    exit_bar, exit_px, reason = u, target, "target"
                    break
                if bars_held >= p.max_hold:
                    exit_bar, exit_px, reason = u, c[u], "time"
                    break
            else:
                if h[u] >= cur_stop:
                    exit_bar, exit_px, reason = u, cur_stop, "stop"
                    break
                if not be_done and cfg.be_at_r > 0 and l[u] <= fill_px - cfg.be_at_r * risk_per_unit:
                    cur_stop = fill_px
                    be_done = True
                if not partial_done and cfg.partial_r > 0 and l[u] <= fill_px - cfg.partial_r * risk_per_unit:
                    trig = fill_px - cfg.partial_r * risk_per_unit
                    partial_pnl = remaining * 0.5 * (trig - fill_px) * sig.side
                    remaining *= 0.5
                    cur_stop = min(cur_stop, fill_px)
                    partial_done = True
                if cur_stop < sig.stop and h[u] >= cur_stop:
                    exit_bar, exit_px, reason = u, cur_stop, "stop"
                    break
                if l[u] <= target:
                    exit_bar, exit_px, reason = u, target, "target"
                    break
                if bars_held >= p.max_hold:
                    exit_bar, exit_px, reason = u, c[u], "time"
                    break
        if exit_bar < 0:
            # still open at the end of data: mark to market
            exit_bar, exit_px, reason = n - 1, c[n - 1], "eod"

        # ---- pnl ----
        gross = partial_pnl + remaining * (exit_px - fill_px) * sig.side
        cost = units * (fill_px + exit_px) * cfg.cost_bps / 1e4
        pnl = gross - cost
        r_mult = gross / (units * risk_per_unit)
        equity += pnl
        busy_until = exit_bar

        trades.append(
            Trade(
                side=sig.side,
                entry_date=idx[fill_bar],
                entry=fill_px,
                stop=sig.stop,
                target=sig.target,
                exit_date=idx[exit_bar],
                exit=exit_px,
                units=units,
                pnl=pnl,
                r_multiple=r_mult,
                bars_held=exit_bar - fill_bar,
                exit_reason=reason,
                rr_planned=sig.rr,
            )
        )
        eq_trades.append((fill_bar, exit_bar, units, fill_px, sig.side, pnl))

    # ---- mark-to-market equity curve (O(n + trades) via difference arrays) ----
    # A trade is marked to market on bars [i0, i1-1] and its pnl is booked from
    # bar i1 (the exit bar) onward.
    open_units = np.zeros(n + 1)
    open_cost = np.zeros(n + 1)
    realized = np.zeros(n + 1)
    for i0, i1, units, fill_px, side, pnl in eq_trades:
        us = units * side
        open_units[i0] += us
        open_units[i1] -= us
        open_cost[i0] += us * fill_px
        open_cost[i1] -= us * fill_px
        realized[i1] += pnl
    eq = (cfg.initial_equity
          + np.cumsum(realized)[:n]
          + np.cumsum(open_units)[:n] * c
          - np.cumsum(open_cost)[:n])
    equity_curve = eq

    curve = pd.Series(equity_curve, index=idx, name="equity")
    return curve, trades


def performance_stats(curve: pd.Series, trades: list[Trade], benchmark: pd.Series | None = None) -> dict:
    ret = curve.pct_change().dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    total_ret = curve.iloc[-1] / curve.iloc[0] - 1
    cagr = (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else np.nan
    downside = ret[ret < 0].std()
    sortino = ret.mean() / downside * np.sqrt(252) if downside and downside > 0 else np.nan
    dd = curve / curve.cummax() - 1
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan

    pnls = np.array([t.pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    profit_factor = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.inf
    rs = np.array([t.r_multiple for t in trades])

    stats = {
        "start": str(curve.index[0].date()),
        "end": str(curve.index[-1].date()),
        "years": round(years, 2),
        "total_return": round(total_ret * 100, 1),
        "cagr": round(cagr * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_dd": round(max_dd * 100, 1),
        "calmar": round(calmar, 2),
        "trades": len(trades),
        "win_rate": round(100 * len(wins) / len(trades), 1) if len(trades) else np.nan,
        "profit_factor": round(profit_factor, 2),
        "avg_r": round(rs.mean(), 2) if len(rs) else np.nan,
        "avg_win": round(wins.mean(), 0) if len(wins) else np.nan,
        "avg_loss": round(losses.mean(), 0) if len(losses) else np.nan,
        "avg_bars_held": round(np.mean([t.bars_held for t in trades]), 1) if trades else np.nan,
        "longs": sum(1 for t in trades if t.side == 1),
        "shorts": sum(1 for t in trades if t.side == -1),
        "exposure": round(100 * sum(t.bars_held + 1 for t in trades) / len(curve), 1),
    }
    if benchmark is not None:
        b = benchmark / benchmark.iloc[0]
        stats["bh_return"] = round((b.iloc[-1] - 1) * 100, 1)
        bdd = (b / b.cummax() - 1).min()
        stats["bh_max_dd"] = round(bdd * 100, 1)
        bret = b.pct_change().dropna()
        stats["bh_sharpe"] = round(bret.mean() / bret.std() * np.sqrt(252), 2) if bret.std() > 0 else np.nan
    return stats