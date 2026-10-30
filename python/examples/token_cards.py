"""A token's launch sky and two tokens compared by sky geometry, saved as SVG cards ($0.25 per call each).

Launch times are block times you look up (contract deployment): USDC 2018-08-03 19:28:24 UTC (Ethereum block
6082465), UNI 2020-09-14 18:11:26 UTC (block 10861674). Data for your own analysis — never a signal or forecast.
Run with ASTRO_CREDITS_TOKEN set (or pay per call over x402)."""
from astro_agents import Client, verify_dataframe

client = Client()
usdc = client.token_chart(launch_datetime="2018-08-03T19:28:24Z", symbol="USDC", name="USD Coin", chain="ethereum",
                          address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", start="2026-11-01", days=120)
print(usdc.attrs["planets"][["sign", "deg", "retrograde"]])
print(usdc[["time", "label"]].head(10))
with open("usdc_launch_sky.svg", "w", encoding="utf-8") as f:
    f.write(usdc.attrs["svg"])

pair = client.token_synastry(a={"launch_datetime": "2018-08-03T19:28:24Z", "symbol": "USDC"},
                             b={"launch_datetime": "2020-09-14T18:11:26Z", "symbol": "UNI"})
print("geometry score:", pair.attrs["score"]["geometry_score"], pair.attrs["aspect_counts"])
print("\n".join(pair.attrs["tightest"]))
with open("usdc_x_uni.svg", "w", encoding="utf-8") as f:
    f.write(pair.attrs["svg"])
assert verify_dataframe(usdc) and verify_dataframe(pair)   # result_sha256 recomputed offline
