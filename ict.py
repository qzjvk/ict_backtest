"""
ICT (Inner Circle Trader) concept detection on OHLC bars.

Concepts implemented:
  - Swing highs / lows (fractal, k-bar confirmation)
  - Market structure: trend state, BOS (break of structure), CHoCH (change of character)
  - Liquidity sweeps (stop hunts): wick takes out a prior swing, close back inside
  - Fair Value Gaps (FVG): 3-candle imbalance
  - Order Blocks (OB): last counter-trend candle before a displacement move
  - Premium / Discount: position of price within the most recent swing range
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Wilder's ATR."""
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(df), np.nan)
    out[period] = tr[1 : period + 1].mean()
    alpha = 1.0 / period
    for i in range(period + 1, len(df)):
        out[i] = out[i - 1] * (1 - alpha) + tr[i] * alpha
    return out


def swing_points(df: pd.DataFrame, k: int = 2):
    """
    Fractal swing points. A bar i is a swing high if its high is strictly the
    max of the window [i-k, i+k]; same for swing low. A swing at bar i is only
    *confirmed* at bar i+k (no lookahead).
    Returns (sh, sl) arrays of swing values at the swing bar index (NaN elsewhere).
    """
    high = df["High"].values
    low = df["Low"].values
    n = len(df)
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    for i in range(k, n - k):
        win_h = high[i - k : i + k + 1]
        win_l = low[i - k : i + k + 1]
        if high[i] == win_h.max() and high[i] > high[i - 1] and high[i] > high[i + 1]:
            sh[i] = high[i]
        if low[i] == win_l.min() and low[i] < low[i - 1] and low[i] < low[i + 1]:
            sl[i] = low[i]
    return sh, sl


def last_swings(sh: np.ndarray, sl: np.ndarray, k: int):
    """
    For each bar t, the most recent swing high/low that is *confirmed* by t
    (i.e. swing index <= t - k). Returns (last_sh, last_sl, last_sh_i, last_sl_i).
    """
    n = len(sh)
    last_sh = np.full(n, np.nan)
    last_sl = np.full(n, np.nan)
    last_sh_i = np.full(n, -1, dtype=int)
    last_sl_i = np.full(n, -1, dtype=int)
    cur_sh, cur_sl = np.nan, np.nan
    cur_sh_i, cur_sl_i = -1, -1
    for t in range(n):
        j = t - k
        if j >= 0:
            if not np.isnan(sh[j]):
                cur_sh, cur_sh_i = sh[j], j
            if not np.isnan(sl[j]):
                cur_sl, cur_sl_i = sl[j], j
        last_sh[t] = cur_sh
        last_sl[t] = cur_sl
        last_sh_i[t] = cur_sh_i
        last_sl_i[t] = cur_sl_i
    return last_sh, last_sl, last_sh_i, last_sl_i


def market_structure(df: pd.DataFrame, k: int = 2):
    """
    Trend state and structure breaks, all computed with confirmed swings only.

    Persistent trend state:
      trend = +1 when close > last confirmed swing high
              -1 when close < last confirmed swing low
              otherwise the previous state persists.
    choch_up[t] : trend flips -1 -> +1 (close above last swing high while
                  structure was down) = change of character / reversal
    bos_up[t]   : close above last swing high while trend already +1
                  (continuation / break of structure)
    """
    close = df["Close"].values
    sh, sl = swing_points(df, k)
    last_sh, last_sl, last_sh_i, last_sl_i = last_swings(sh, sl, k)

    n = len(close)
    trend = np.zeros(n, dtype=int)
    bos_up = np.zeros(n, dtype=bool)
    bos_dn = np.zeros(n, dtype=bool)
    choch_up = np.zeros(n, dtype=bool)
    choch_dn = np.zeros(n, dtype=bool)

    state = 0
    for t in range(n):
        if np.isnan(last_sh[t]) or np.isnan(last_sl[t]):
            trend[t] = state
            continue
        if close[t] > last_sh[t]:
            new = 1
        elif close[t] < last_sl[t]:
            new = -1
        else:
            new = state
        if state == -1 and new == 1:
            choch_up[t] = True
        if state == 1 and new == -1:
            choch_dn[t] = True
        if state == 1 and new == 1 and close[t] > last_sh[t]:
            bos_up[t] = True
        if state == -1 and new == -1 and close[t] < last_sl[t]:
            bos_dn[t] = True
        state = new
        trend[t] = state

    return {
        "trend": trend,
        "bos_up": bos_up,
        "bos_dn": bos_dn,
        "choch_up": choch_up,
        "choch_dn": choch_dn,
        "last_sh": last_sh,
        "last_sl": last_sl,
        "last_sh_i": last_sh_i,
        "last_sl_i": last_sl_i,
    }


def liquidity_sweeps(df: pd.DataFrame, k: int = 2):
    """
    Sweep of a prior swing: the bar's wick takes out the last confirmed swing
    but the close finishes back inside it (stop hunt / liquidity grab).
    """
    close = df["Close"].values
    high = df["High"].values
    low = df["Low"].values
    sh, sl = swing_points(df, k)
    last_sh, last_sl, _, _ = last_swings(sh, sl, k)

    n = len(close)
    sweep_low = np.zeros(n, dtype=bool)   # wicked below last swing low, closed above
    sweep_high = np.zeros(n, dtype=bool)  # wicked above last swing high, closed below
    for t in range(n):
        if np.isnan(last_sl[t]):
            continue
        if low[t] < last_sl[t] and close[t] > last_sl[t]:
            sweep_low[t] = True
        if np.isnan(last_sh[t]):
            continue
        if high[t] > last_sh[t] and close[t] < last_sh[t]:
            sweep_high[t] = True
    return sweep_low, sweep_high


def fair_value_gaps(df: pd.DataFrame):
    """
    3-candle FVG.
    Bullish FVG at bar t: low[t] > high[t-2]  -> zone [high[t-2], low[t]]
    Bearish FVG at bar t: high[t] < low[t-2]  -> zone [high[t], low[t-2]]
    Returns (bull_top, bull_bot, bear_top, bear_bot) arrays (NaN when absent).
    """
    high = df["High"].values
    low = df["Low"].values
    n = len(df)
    bull_top = np.full(n, np.nan)
    bull_bot = np.full(n, np.nan)
    bear_top = np.full(n, np.nan)
    bear_bot = np.full(n, np.nan)
    for t in range(2, n):
        if low[t] > high[t - 2]:
            bull_top[t] = low[t]
            bull_bot[t] = high[t - 2]
        if high[t] < low[t - 2]:
            bear_top[t] = low[t - 2]
            bear_bot[t] = high[t]
    return bull_top, bull_bot, bear_top, bear_bot


def order_blocks(df: pd.DataFrame, k: int = 2, disp_atr: float = 1.0):
    """
    Order block: the last counter-trend candle immediately before a
    displacement candle that breaks structure.
    Bullish OB at t: candle t-1 bearish, candle t is a bullish displacement
    breaking the last confirmed swing high. Zone = [low[t-1], high[t-1]].
    """
    o = df["Open"].values
    c = df["Close"].values
    h = df["High"].values
    l = df["Low"].values
    a = atr(df)
    m = market_structure(df, k)
    n = len(df)
    ob_bull_top = np.full(n, np.nan)
    ob_bull_bot = np.full(n, np.nan)
    ob_bear_top = np.full(n, np.nan)
    ob_bear_bot = np.full(n, np.nan)
    for t in range(2, n):
        if np.isnan(a[t]) or np.isnan(m["last_sh"][t]) or np.isnan(m["last_sl"][t]):
            continue
        bull_disp = c[t] > o[t] and (c[t] - o[t]) >= disp_atr * a[t] and c[t] > m["last_sh"][t]
        bear_disp = c[t] < o[t] and (o[t] - c[t]) >= disp_atr * a[t] and c[t] < m["last_sl"][t]
        if bull_disp and c[t - 1] < o[t - 1]:
            ob_bull_top[t] = h[t - 1]
            ob_bull_bot[t] = l[t - 1]
        if bear_disp and c[t - 1] > o[t - 1]:
            ob_bear_top[t] = l[t - 1]
            ob_bear_bot[t] = h[t - 1]
    return ob_bull_top, ob_bull_bot, ob_bear_top, ob_bear_bot


def premium_discount(df: pd.DataFrame, k: int = 2):
    """
    Position of the close within the most recent confirmed swing range
    [last_sl, last_sh]. 0 = at the low (deep discount), 1 = at the high
    (deep premium). NaN when the range is not defined.
    """
    close = df["Close"].values
    m = market_structure(df, k)
    n = len(close)
    pos = np.full(n, np.nan)
    for t in range(n):
        if np.isnan(m["last_sh"][t]) or np.isnan(m["last_sl"][t]):
            continue
        rng = m["last_sh"][t] - m["last_sl"][t]
        if rng <= 0:
            continue
        pos[t] = (close[t] - m["last_sl"][t]) / rng
    return pos