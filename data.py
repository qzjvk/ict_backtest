"""Data loading: Yahoo Finance continuous futures (ES=F, NQ=F), cached to CSV.

Intervals (Yahoo limits):
  1d   -> full history
  1h   -> last 730 days
  15m  -> last 60 days
  5m   -> last 60 days
  1m   -> last 7-8 days
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE = Path(__file__).parent / "data"

SYMBOLS = {
    "ES": "ES=F",   # E-mini S&P 500
    "NQ": "NQ=F",   # E-mini Nasdaq 100
}

INTERVAL_PERIOD = {
    "1d": "max",
    "1h": "730d",
    "90m": "60d",
    "30m": "60d",
    "15m": "60d",
    "5m": "60d",
    "2m": "60d",
    "1m": "8d",
}


def load(name: str = "ES", interval: str = "1d", refresh: bool = False) -> pd.DataFrame:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{name}_{interval}.csv"
    if path.exists() and not refresh:
        df = pd.read_csv(path)
        df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
        return df.set_index("Date")

    period = INTERVAL_PERIOD[interval]
    df = yf.Ticker(SYMBOLS[name]).history(period=period, interval=interval, auto_adjust=False)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.index = df.index.tz_localize(None)
    df.index.name = "Date"
    df.to_csv(path)
    return df