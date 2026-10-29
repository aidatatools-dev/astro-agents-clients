"""Merge the celestial event calendar onto daily OHLC candles, then compare returns around events.

    pip install astro-agents          # + optionally yfinance
    export ASTRO_CREDITS_TOKEN=astc_...   # 3 years of events = 3 calls x $0.25
    python events_ohlc_merge.py

An event study, not a trading signal: it measures, it does not predict.
"""
import pandas as pd

from astro_agents import Client, merge_events, verify_dataframe
from _candles import load_candles

client = Client()
candles = load_candles("BTC-USD", "2022-01-01", "2024-12-31")
events = client.events("2022-01-01", "2024-12-31", include=["station", "eclipse", "ingress"])
assert verify_dataframe(events)                       # every result hash recomputed offline

# Each event onto the candle whose day contains it (events are timed to the UTC minute)
day = events["time"].dt.floor("D").astype(candles["open_time"].dtype)
per_day = events.groupby(day)["key"].size()
df = candles.copy()
df["n_events"] = df["open_time"].dt.floor("D").map(per_day).fillna(0).astype(int)
# Or the latest event at or before each candle, in one call:
latest = merge_events(candles, events, on="open_time", tolerance="3D")
df["ret_next"] = df["close"].pct_change().shift(-1)

# Average next-day return on event days vs other days
print(df.groupby(df["n_events"] > 0)["ret_next"].describe())

# Mercury stations: the next 5 days' return after each one
stations = events[(events["type"] == "station") & (events["body"] == "mercury")]
fwd = []
for t in stations["time"]:
    window = candles[candles["open_time"] >= t.floor("D")].head(6)
    if len(window) == 6:
        fwd.append(window["close"].iloc[-1] / window["close"].iloc[0] - 1)
print(f"Mercury stations: {len(fwd)}, mean 5-day return {pd.Series(fwd).mean():+.2%}")

# Keep the provenance with the study: same request, same bytes
print("result hashes:", events.attrs["result_sha256"])
