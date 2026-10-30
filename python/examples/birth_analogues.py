"""Birth-sky analogues: the dates whose sky most resembles a birth chart, past and future.

    pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"
    export ASTRO_CREDITS_TOKEN=astc_...   # 3 calls x $0.25
    python birth_analogues.py

Compare a birth sky to past/future dates, data only. The local birth time is resolved like
western/positions (time zone from the coordinates); a date alone is computed at 12:00 with a
TIME_UNKNOWN warning (the Moon is then approximate; Jupiter to Pluto stay reliable). No houses or
ascendant. Each date is ranked by a stated angular distance (df.attrs["metric"]): it finds matching
positions and says nothing about what will happen. Data for your own analysis, never a signal or forecast.
"""
from datetime import datetime, timezone

from astro_agents import Client, verify_dataframe

client = Client()
birth = dict(birth="1990-05-15T14:30", latitude=48.8566, longitude=2.3522)   # local time, Paris
slow = ["jupiter", "saturn", "uranus", "neptune", "pluto"]
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# 1. The 50 years either side of the birth: the dates whose slow-planet sky is closest, one per passage
both = client.analogues(**birth, direction="both", bodies=slow, min_separation_days=3650, top_n=5)
print(both[["time", "days_from_reference", "score", "geo.jupiter", "geo.saturn", "geo.pluto"]])

# 2. From today to 2099: the next dates whose sky resembles the birth sky, angles and retrograde flags included
future = client.analogues(**birth, start=today, end="2099-12-31", resolution="1w", bodies=slow,
                          features=["longitude", "aspects", "retrograde"], min_separation_days=365, top_n=5)
print(future[["time", "score", "geo.jupiter-saturn:angle"]])

# 3. Birth time unknown: computed at 12:00 local, with a warning that says which positions stay reliable
noon = client.analogues(birth="1990-05-15", latitude=48.8566, longitude=2.3522, direction="past", bodies=slow,
                        min_separation_days=3650, top_n=3)
print([w["code"] for w in noon.attrs["warnings"]])

# The resolved birth moment, and the same request with the positions written out: same result, same hash
res = both.attrs["reference_resolution"]
print(res["time"]["utc"], res["equivalent_request"]["reference"]["values"])
for df in (both, future, noon):
    assert verify_dataframe(df)           # result hashes recomputed offline
    print(df.attrs["meta"]["input_sha256"], df.attrs["result_sha256"])
