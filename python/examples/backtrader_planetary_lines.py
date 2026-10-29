"""Feed Gann planetary lines to backtrader as extra data lines.

    pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"
    pip install backtrader   # + optionally yfinance
    export ASTRO_CREDITS_TOKEN=astc_...   # 3 years daily = 2 calls x $0.20
    python backtrader_planetary_lines.py

The strategy shows how to read a planetary line inside backtrader; it is not a trading signal.
"""
import backtrader as bt
import pandas as pd

from astro_agents import Client
from _candles import load_candles

client = Client()
candles = load_candles("BTC-USD", "2022-01-01", "2024-12-31").set_index("open_time")
lines = client.planetary_lines(start="2022-01-01", end="2024-12-31", bodies=["mars"], perspective="geocentric")

df = candles.join(lines[["geo.mars"]].reindex(candles.index.floor("D")).set_axis(candles.index), how="left")
df = df.rename(columns={"geo.mars": "mars"}).ffill()
df.index = df.index.tz_convert(None)          # backtrader wants naive datetimes


class AstroData(bt.feeds.PandasData):
    lines = ("mars",)
    params = (("mars", "mars"),)


class MarsSignChange(bt.Strategy):
    """Example: enter when Mars changes zodiac sign (every 30 degrees), exit 10 bars later."""

    def __init__(self):
        self.entry_bar = None

    def next(self):
        sign_now, sign_before = int(self.data.mars[0] // 30), int(self.data.mars[-1] // 30)
        if not self.position and sign_now != sign_before:
            self.buy()
            self.entry_bar = len(self)
        elif self.position and len(self) - self.entry_bar >= 10:
            self.close()


cerebro = bt.Cerebro()
cerebro.adddata(AstroData(dataname=df))
cerebro.addstrategy(MarsSignChange)
cerebro.broker.setcash(10_000)
cerebro.broker.setcommission(commission=0.001)
cerebro.addsizer(bt.sizers.PercentSizer, percents=95)
cerebro.run()
print(f"final value: {cerebro.broker.getvalue():,.2f} (start 10,000)")
print("line data hashes:", lines.attrs["result_sha256"])
