"""Minimal Freqtrade strategy with Astro Agents data as features (a data source, not a signal).

Copy into user_data/strategies/, set ASTRO_CREDITS_TOKEN in the bot's environment, and add
`astro-agents` to the bot's Python environment (pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python").

    freqtrade backtesting --strategy AstroDataStrategy --timeframe 1d --timerange 20230101-20241231

The calendar and the lines are fetched once per pair and range, then cached in memory (the same
request always returns the same bytes, so caching on the request is safe). The entry/exit rules
below only show where the columns plug in; replace them with your own.
"""
from functools import lru_cache

import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame

from astro_agents import Client

_client = Client()


@lru_cache(maxsize=32)
def _events(start: str, end: str) -> pd.DataFrame:
    return _client.events(start, end, include=["station", "eclipse", "ingress"])


@lru_cache(maxsize=32)
def _lines(start: str, end: str) -> pd.DataFrame:
    return _client.planetary_lines(start=start, end=end, bodies=["jupiter", "saturn"], perspective="heliocentric")


class AstroDataStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1d"
    minimal_roi = {"0": 0.10}
    stoploss = -0.08
    startup_candle_count = 2

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        start = dataframe["date"].min().strftime("%Y-%m-%d")
        end = dataframe["date"].max().strftime("%Y-%m-%d")
        day = dataframe["date"].dt.floor("D")

        ev = _events(start, end)
        if not ev.empty:
            per_day = ev.assign(day=ev["time"].dt.floor("D")).groupby("day")["key"].size()
            dataframe["astro_events"] = day.map(per_day).fillna(0).astype(int)
            stations = ev[ev["type"] == "station"].assign(day=lambda d: d["time"].dt.floor("D"))
            dataframe["astro_station"] = day.isin(set(stations["day"])).astype(int)
        else:
            dataframe["astro_events"] = 0
            dataframe["astro_station"] = 0

        lines = _lines(start, end)
        dataframe["helio_jupiter"] = day.map(lines["helio.jupiter"]).ffill()
        dataframe["helio_saturn"] = day.map(lines["helio.saturn"]).ffill()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Placeholder rule (illustration only): enter on a day with no event after a day with a station
        dataframe.loc[(dataframe["astro_station"].shift(1) == 1) & (dataframe["astro_events"] == 0),
                      "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["astro_station"] == 1, "exit_long"] = 1
        return dataframe
