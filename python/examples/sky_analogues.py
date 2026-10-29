"""Matching skies: today's past analogues, and the next dates with a similar sky.

    pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"
    export ASTRO_CREDITS_TOKEN=astc_...   # 3 calls x $0.25
    python sky_analogues.py

finance/analogues ranks dates by a stated angular distance between two skies (the formula is in
df.attrs["metric"]). It finds matching positions; it says nothing about what will happen.
Data for your own analysis, never a signal or forecast.
"""
from datetime import datetime, timezone

from astro_agents import Client, verify_dataframe

client = Client()
today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00Z")   # pin the reference: same request, same bytes
slow = ["jupiter", "saturn", "uranus", "neptune", "pluto"]

# 1. Past analogues of today's slow-planet sky, at least 10 years apart (one match per passage)
past = client.analogues(today, direction="past", bodies=slow, min_separation_days=3650, top_n=5)
print(past[["time", "score", "geo.jupiter", "geo.saturn", "geo.pluto"]])

# 2. The next skies like today's, weighting the Jupiter-Saturn angle and matching retrograde flags too
future = client.analogues(today, direction="future", bodies=slow, features=["longitude", "aspects", "retrograde"],
                          weights={"geo.jupiter-saturn:angle": 3}, min_separation_days=365, top_n=5)
print(future[["time", "days_from_reference", "score", "geo.jupiter-saturn:angle"]])

# 3. Your own configuration: every Jupiter-Saturn conjunction with Mars retrograde, 1900-2099, weekly grid
conj = client.analogues({"geo.jupiter-saturn:angle": 0, "geo.mars:retrograde": True}, start="1900-01-01",
                        end="2099-12-31", resolution="1w", min_separation_days=365, top_n=10)
print(conj[["time", "score", "geo.jupiter-saturn:angle", "geo.mars:retrograde"]])

# Each row shows how its score was computed: distance:<feature id> columns, averaged with the weights
print(past.attrs["metric"]["score"])
for df in (past, future, conj):
    assert verify_dataframe(df)           # result hashes recomputed offline
    print(df.attrs["meta"]["input_sha256"], df.attrs["result_sha256"])
