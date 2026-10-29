"""OHLC candles for the examples: your CSV (open_time,open,high,low,close,volume), Yahoo Finance when
yfinance is installed, or a clearly labelled synthetic series so every example runs offline."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd


def load_candles(symbol: str = "BTC-USD", start: str = "2022-01-01", end: str = "2024-12-31") -> pd.DataFrame:
    """Daily candles with a UTC `open_time` column, sorted."""
    path = os.environ.get("CANDLES_CSV")
    if path:
        df = pd.read_csv(path)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        return df.sort_values("open_time").reset_index(drop=True)
    try:
        import yfinance as yf
        df = yf.download(symbol, start=start, end=end, interval="1d", progress=False, auto_adjust=True)
        if len(df):
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df.reset_index().rename(columns={"Date": "open_time", "date": "open_time"})
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            return df[["open_time", "open", "high", "low", "close", "volume"]]
    except Exception:  # noqa: BLE001 -- yfinance missing or offline: fall through
        pass
    print("note: synthetic random-walk candles (set CANDLES_CSV or pip install yfinance for real data)", file=sys.stderr)
    idx = pd.date_range(start, end, freq="D", tz="UTC")
    rng = np.random.default_rng(7)
    close = 20_000 * np.exp(np.cumsum(rng.normal(0, 0.03, len(idx))))
    return pd.DataFrame({"open_time": idx, "open": close, "high": close * 1.02, "low": close * 0.98,
                         "close": close, "volume": 1.0})
