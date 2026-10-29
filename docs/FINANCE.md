# Financial astrology data for backtesting

Verifiable, reproducible astro-financial data for backtesting: geocentric and heliocentric positions,
declination, Gann planetary lines and a celestial event calendar. **The only astro-finance data source that
is provable and replayable:** every response carries `meta.input_sha256` and `meta.result_sha256`, and the same
request returns the same bytes on any machine, today or in five years for the same engine version.

This is **data, not signals**. Nothing here forecasts a price or recommends a trade. The numbers are positions
and event times from NASA/JPL DE440 (1800–2200); what a strategy does with them is the strategy's business.

| Route | MCP tool | Price | What |
|---|---|---|---|
| `POST /v1/finance/planetary-lines` | `planetary_lines` | $0.20 | Gann lines: degrees geo + helio, aspect offsets, Mean of 5 / Circle of 8, price levels, snapshot or series |
| `POST /v1/finance/events` | `astro_event_calendar` | $0.25 | Ingresses, stations, lunations, eclipses, aspects, parallels, out-of-bounds, to the minute |
| `POST /v1/finance/analogues` | `sky_analogues` | $0.25 | Matching skies: the past or future dates whose positions best match a reference sky, ranked by a stated angular distance |
| `POST /v1/western/positions` | `planet_positions` | $0.01 | `options.perspective: "heliocentric"`, `options.coordinates: "equatorial"` |
| `POST /v1/western/aspects` | `aspects` | $0.02 | `options.declination: true` (parallels / contra-parallels) |
| `POST /v1/western/sky` | `sky_today` | $0.01 | The sky now and the next 1–90 days of events |

Prices are those of catalog.py; a deployment can still override them (`ASTRO_PRICE_FINANCE_PLANETARY_LINES`,
`ASTRO_PRICE_FINANCE_EVENTS`).

## What is better than the desktop suites

- **Reproducible and citable.** A backtest can store the input and result hashes and prove later that it ran on
  exactly these numbers (`POST /v1/verify` recomputes a hash). Desktop suites and free scripts can't do this.
- **Geocentric and heliocentric in one call**, as aligned columns of a single series.
- **Event times to the minute**, not only daily samples. This covers stations, eclipses with gamma and magnitude,
  and declination parallels and out-of-bounds crossings, which few tools time at all.
- **Accuracy you can check.** Positions are verified against NASA/JPL Horizons ([BENCHMARK.md](https://astro-agent.dev/benchmark.md)).
  Eclipses agree with NASA's canon to the minute, and the type, gamma and magnitude agree too
  (`tests/test_finance.py`).
- **Every convention is stated in the response:** frame, perspective, averaging rule, price formula and precision.

## Conventions

- **Geocentric:** apparent positions on the true ecliptic and equinox of date. This is the same as every other
  route.
- **Heliocentric:** geometric positions, meaning the instantaneous Sun-to-body vector with no light-time, on the
  same ecliptic. The Earth takes the Sun's place. The Moon and the lunar nodes have no heliocentric line.
- **Declination:** measured on the true equator of date. A body is "out of bounds" when |declination| is greater
  than the true obliquity.
- **Averages (Optuma's definitions):**
  - Mean of 5 = (Jupiter + Saturn + Uranus + Neptune + Pluto) / 5;
  - Circle of 8 = (Mercury + … + Pluto) / 8.

  Both are arithmetic means of the 0–360 longitudes, computed in each perspective. `average_method: "circular"`
  gives the vector mean instead. With `unwrap`, the mean is taken over the unwrapped members, so the line stays
  continuous.
- **Price levels:** `price = (degree + 360·k) × price_unit`, for every integer k inside `price_range`. A line at
  100° with a unit of $1 gives $100, $460, $820 and so on.
- **Line ids:** `geo.jupiter`, `helio.saturn+90`, `geo.mean_of_5+180`. The degree of a line is
  (longitude + offset) mod 360.

## Consuming it from a bot

The output is plain JSON with flat, stable field names. Times are given both as `exact_utc` / `time_utc`
(ISO 8601, UTC minute) and as `timestamp` (unix seconds), so they join directly on candle open times.

### Series to a DataFrame

```bash
curl -X POST https://astro-agent.dev/v1/finance/planetary-lines -H 'Content-Type: application/json' \
  -d '{"start":"2024-01-01","end":"2024-01-03","bodies":["jupiter"],"averages":["mean_of_5"]}'
```

`result.series` (real output, engine 1.4.0):

```json
{"time_utc": ["2024-01-01T00:00Z", "2024-01-02T00:00Z", "2024-01-03T00:00Z"],
 "timestamp": [1704067200, 1704153600, 1704240000],
 "geo.jupiter": [35.582393, 35.587194, 35.595453],
 "geo.mean_of_5": [214.52874, 214.552382, 214.577222],
 "helio.jupiter": [45.836832, 45.927269, 46.017694],
 "helio.mean_of_5": [218.425543, 218.454479, 218.483408]}
```

```python
import pandas as pd
lines = pd.DataFrame(resp["result"]["series"]).set_index("timestamp")
candles = candles.join(lines, on="open_time_s")        # one feature column per line
```

Limits:

- at most 1000 samples per call (`interval` 1h, 4h, 12h, 1d or 1w);
- longer histories are paged by date range;
- `format: "rows"` returns one object per sample instead.

### Events

```bash
curl -X POST https://astro-agent.dev/v1/finance/events -H 'Content-Type: application/json' \
  -d '{"start":"2024-04-01","end":"2024-04-10","include":["station","eclipse"]}'
```

`result.events` (real output; `result_sha256` 615fd275…cf3):

```json
[{"type": "station", "body": "mercury", "turns": "retrograde", "longitude": 27.218618,
  "position": "27°13'07\" Aries", "exact_utc": "2024-04-01T22:14Z", "timestamp": 1712009640,
  "key": "station:mercury:retrograde:2024-04-01T22:14Z"},
 {"type": "eclipse", "kind": "solar", "eclipse_type": "total", "gamma": 0.343139, "central": true,
  "umbral_radius_earth_radii": -0.010591, "sun_position": "19°23'53\" Aries",
  "moon_position": "19°21'50\" Aries", "exact_utc": "2024-04-08T18:17Z", "timestamp": 1712600220,
  "key": "eclipse:solar:total:2024-04-08T18:17Z"}]
```

- Each call covers up to 366 days. Page a backtest year by year (1800–2200), then de-duplicate on `key`.
- The event types are `ingress`, `station`, `lunation`, `eclipse`, `aspect`, `declination` (parallel /
  contraparallel) and `out_of_bounds`. In the heliocentric perspective only `ingress` and `aspect` exist.
- `include_moon: true` adds the Moon's ingresses, aspects, parallels and out-of-bounds crossings, about a
  thousand events a year.

### Plugins for bot frameworks

The output is already shaped so that an adapter for Freqtrade, OctoBot, Superalgos or Jesse is short:

1. fetch the events or series for the backtest range (cache them on `meta.input_sha256`);
2. merge on `timestamp`;
3. expose the columns as features or informative pairs.

The official Python client ([clients/python](../python), `pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"`) already does this.
`planetary_lines()` and `events()` return DataFrames and page long ranges. `merge_events()` joins the calendar
onto candles. The [examples](../python/examples) cover vectorbt, backtrader and a minimal Freqtrade strategy
that uses the data as features. No plugin is published inside those frameworks' own repositories.

## Precision

- **Event times:** ±1 minute (UTC). Stations and slow declination crossings are flat, so their minute is the
  least sharp.
- **Series:** use IAU 2000B nutation, which differs from the snapshot (IAU 2000A) by about 1 mas.
- **Values:** rounded to 1e-6 in the result, which is what the hash covers.
