"""
ICT strategy: "Sweep -> Displacement -> FVG re-entry"

Long setup (signal at close of bar t):
  1. Liquidity sweep: within the last `sweep_lookback` bars, price wicked below
     the last confirmed swing low and closed back above it (stop hunt).
  2. Displacement: bar t is a strong bullish candle (body >= disp_atr * ATR)
     that closes above the last confirmed swing high (structure break).
  3. Fair Value Gap: the displacement leaves a bullish FVG (low[t] > high[t-2]).
  4. (optional) Structure mode: "any" break, "choch" (reversal) or "bos"
     (continuation) only.
  5. (optional) Premium/Discount: the FVG equilibrium must sit in discount
     (< 50% of the most recent swing range) for longs, premium for shorts.
  Entry: limit at the FVG edge (first bar that trades into the zone; fill at
  open if the bar opens inside the zone). Stop beyond the sweep extreme.
  Target: the last confirmed swing high (opposing liquidity pool).

Shorts are the exact mirror.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ict import atr, fair_value_gaps, liquidity_sweeps, market_structure


@dataclass
class Params:
    k: int = 2                 # swing fractal depth
    atr_period: int = 14
    disp_atr: float = 0.4      # displacement body threshold in ATR units
    sweep_lookback: int = 15   # sweep must occur within this many bars before displacement
    max_wait: int = 5          # bars to wait for FVG fill before cancelling
    max_hold: int = 15         # time stop (bars)
    min_rr: float = 1.0        # minimum reward:risk to the opposing swing
    stop_buf_atr: float = 0.25 # stop buffer beyond the sweep extreme
    structure: str = "any"     # "any" | "choch" | "bos"
    use_pd: bool = False       # premium/discount filter on the FVG equilibrium
    use_fvg_entry: bool = True # enter on FVG re-entry (False: enter next open)
    require_sweep: bool = True # require the liquidity sweep
    use_trend: bool = False    # longs only in up-trend state, shorts only in down
    require_break: bool = False# displacement must close beyond the last swing
    ce_entry: bool = False     # enter at FVG midpoint (CE) instead of the edge


@dataclass
class Signal:
    t: int
    side: int          # +1 long, -1 short
    entry_ref: float   # FVG edge used as limit (NaN -> next open)
    stop: float
    target: float
    sweep_bar: int
    disp_bar: int
    fvg_top: float
    fvg_bot: float
    rr: float


def _find_sweep(sweep: np.ndarray, t: int, lookback: int) -> int:
    for s in range(t - 1, max(t - 1 - lookback, -1), -1):
        if sweep[s]:
            return s
    return -1


def reverse_signals(signals: list[Signal]) -> list[Signal]:
    """Mirror each signal: flip the side and mirror the stop/target around the
    entry reference. Same setup, same entry level, opposite directional bet.

    ICT bets the sweep was a trap (reversal); the reverse bets the sweep was real
    (continuation). Risk and reward distances are preserved, so the RR is unchanged.
    """
    rev: list[Signal] = []
    for s in signals:
        if np.isnan(s.entry_ref):
            continue  # no reference level to mirror around
        new_stop = 2 * s.entry_ref - s.stop
        new_target = 2 * s.entry_ref - s.target
        rev.append(
            Signal(
                t=s.t, side=-s.side, entry_ref=s.entry_ref,
                stop=new_stop, target=new_target,
                sweep_bar=s.sweep_bar, disp_bar=s.disp_bar,
                fvg_top=s.fvg_top, fvg_bot=s.fvg_bot, rr=s.rr,
            )
        )
    return rev


def generate_signals(df: pd.DataFrame, p: Params) -> list[Signal]:
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    n = len(df)

    a = atr(df, p.atr_period)
    m = market_structure(df, p.k)
    sweep_low, sweep_high = liquidity_sweeps(df, p.k)
    bull_top, bull_bot, bear_top, bear_bot = fair_value_gaps(df)

    signals: list[Signal] = []

    # 3-candle FVG: displacement candle is bar t-1 (the big move), the FVG is
    # confirmed by bar t. Bullish FVG at t: low[t] > high[t-2], zone
    # [high[t-2], low[t]] with the top at low[t] (close to the current price,
    # so the retrace entry is shallow).
    for t in range(max(p.k + 2, p.atr_period + 2), n):
        if (np.isnan(a[t]) or np.isnan(a[t - 1])
                or np.isnan(m["last_sh"][t]) or np.isnan(m["last_sl"][t])):
            continue
        rng = m["last_sh"][t] - m["last_sl"][t]

        # ---------------- LONG ----------------
        # displacement: bar t-1 is a strong bullish candle
        bull_disp = (
            c[t - 1] > o[t - 1]
            and (c[t - 1] - o[t - 1]) >= p.disp_atr * a[t - 1]
        )
        has_fvg = not np.isnan(bull_top[t])
        if bull_disp and p.use_fvg_entry and not has_fvg:
            bull_disp = False
        if bull_disp:
            sweep_bar = -1
            if p.require_sweep:
                sweep_bar = _find_sweep(sweep_low, t - 1, p.sweep_lookback)
                if sweep_bar < 0:
                    bull_disp = False
            if bull_disp and p.use_trend and m["trend"][t - 1] != 1:
                bull_disp = False
            if bull_disp and p.require_break and c[t - 1] <= m["last_sh"][t - 1]:
                bull_disp = False
            if bull_disp and p.structure == "choch" and not m["choch_up"][t - 1]:
                bull_disp = False
            if bull_disp and p.structure == "bos" and not m["bos_up"][t - 1]:
                bull_disp = False
            if bull_disp:
                fvg_top = bull_top[t] if has_fvg else np.nan
                fvg_bot = bull_bot[t] if has_fvg else np.nan
                entry_ref = fvg_top if p.use_fvg_entry else np.nan
                if p.use_fvg_entry and p.ce_entry and has_fvg:
                    entry_ref = (fvg_top + fvg_bot) / 2
                stop = min(l[sweep_bar] if sweep_bar >= 0 else l[t - 1], l[t - 1]) - p.stop_buf_atr * a[t]
                target = m["last_sh"][t]
                # premium/discount: FVG equilibrium must be in discount
                if bull_disp and p.use_pd and p.use_fvg_entry and rng > 0:
                    eq = (fvg_top + fvg_bot) / 2 if has_fvg else c[t]
                    if (eq - m["last_sl"][t]) / rng >= 0.5:
                        bull_disp = False
                if bull_disp:
                    entry_est = entry_ref if not np.isnan(entry_ref) else o[t]
                    rr = (target - entry_est) / (entry_est - stop) if entry_est > stop else 0
                    if rr >= p.min_rr and target > entry_est:
                        signals.append(
                            Signal(
                                t=t, side=1, entry_ref=entry_ref, stop=stop,
                                target=target, sweep_bar=sweep_bar, disp_bar=t - 1,
                                fvg_top=fvg_top, fvg_bot=fvg_bot, rr=rr,
                            )
                        )

        # ---------------- SHORT ----------------
        # displacement: bar t-1 is a strong bearish candle
        bear_disp = (
            c[t - 1] < o[t - 1]
            and (o[t - 1] - c[t - 1]) >= p.disp_atr * a[t - 1]
        )
        has_fvg = not np.isnan(bear_top[t])
        if bear_disp and p.use_fvg_entry and not has_fvg:
            bear_disp = False
        if bear_disp:
            sweep_bar = -1
            if p.require_sweep:
                sweep_bar = _find_sweep(sweep_high, t - 1, p.sweep_lookback)
                if sweep_bar < 0:
                    bear_disp = False
            if bear_disp and p.use_trend and m["trend"][t - 1] != -1:
                bear_disp = False
            if bear_disp and p.require_break and c[t - 1] >= m["last_sl"][t - 1]:
                bear_disp = False
            if bear_disp and p.structure == "choch" and not m["choch_dn"][t - 1]:
                bear_disp = False
            if bear_disp and p.structure == "bos" and not m["bos_dn"][t - 1]:
                bear_disp = False
            if bear_disp:
                fvg_top = bear_top[t] if has_fvg else np.nan
                fvg_bot = bear_bot[t] if has_fvg else np.nan
                entry_ref = fvg_bot if p.use_fvg_entry else np.nan
                if p.use_fvg_entry and p.ce_entry and has_fvg:
                    entry_ref = (fvg_top + fvg_bot) / 2
                stop = max(h[sweep_bar] if sweep_bar >= 0 else h[t - 1], h[t - 1]) + p.stop_buf_atr * a[t]
                target = m["last_sl"][t]
                if bear_disp and p.use_pd and p.use_fvg_entry and rng > 0:
                    eq = (fvg_top + fvg_bot) / 2 if has_fvg else c[t]
                    if (eq - m["last_sl"][t]) / rng <= 0.5:
                        bear_disp = False
                if bear_disp:
                    entry_est = entry_ref if not np.isnan(entry_ref) else o[t]
                    rr = (entry_est - target) / (stop - entry_est) if stop > entry_est else 0
                    if rr >= p.min_rr and target < entry_est:
                        signals.append(
                            Signal(
                                t=t, side=-1, entry_ref=entry_ref, stop=stop,
                                target=target, sweep_bar=sweep_bar, disp_bar=t - 1,
                                fvg_top=fvg_top, fvg_bot=fvg_bot, rr=rr,
                            )
                        )

    return signals