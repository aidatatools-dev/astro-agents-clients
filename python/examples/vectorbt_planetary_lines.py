"""Backtest a rule built on a Gann planetary line with vectorbt.

    pip install astro-agents vectorbt     # + optionally yfinance
    export ASTRO_CREDITS_TOKEN=astc_...   # 3 years daily = 2 calls x $0.20
    python vectorbt_planetary_lines.py

The rule is an illustration of the mechanics (a line as a feature), not a trading signal.
"""
import numpy as np
import pandas as pd
import vectorbt as vbt

from astro_agents import Client
from _candles import load_candles

client = Client()
candles = load_candles("BTC-USD", "2022-01-01", "2024-12-31").set_index("open_time")
lines = client.planetary_lines(start="2022-01-01", end="2024-12-31", bodies=["jupiter", "saturn"],
                               averages=["mean_of_5"], unwrap=True)

# Align the daily line values on the candles (both indexed by UTC day)
close = candles["close"]
feat = lines.reindex(close.index.floor("D"), method="ffill")
feat.index = close.index

# Example feature: the heliocentric Jupiter-Saturn angle, folded to 0-180 degrees
angle = (feat["helio.jupiter"] - feat["helio.saturn"]) % 360
angle = np.minimum(angle, 360 - angle)

# Example rule: long while the angle is within 30 degrees of a square (90), flat otherwise
inside = (angle - 90).abs() < 30
entries = inside & ~inside.shift(1, fill_value=False)
exits = ~inside & inside.shift(1, fill_value=False)

pf = vbt.Portfolio.from_signals(close, entries, exits, fees=0.001, freq="1D")
print(pf.stats()[["Total Return [%]", "Max Drawdown [%]", "Total Trades", "Sharpe Ratio"]])
print("buy & hold:", f"{close.iloc[-1] / close.iloc[0] - 1:+.1%}")
print("line data hashes:", lines.attrs["result_sha256"])
