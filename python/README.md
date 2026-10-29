# astro-agents: Python client

[![Python](https://img.shields.io/badge/python-3.9%2B-3776ab)](https://github.com/aidatatools-dev/astro-agents-clients/tree/main/python)
[![API](https://img.shields.io/badge/API-astro--agent.dev-0b7285)](https://astro-agent.dev/v1/catalog)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/aidatatools-dev/astro-agents-clients/blob/main/python/LICENSE)

The official Python client for [Astro Agents](https://astro-agent.dev): verifiable planetary timing data for
market analysis and backtesting, returned as **pandas DataFrames**. The data covers:

- Gann planetary lines and a to-the-minute event calendar;
- geocentric and heliocentric positions, and declination parallels;
- full Western and Vedic astrology.

Everything comes from the NASA/JPL DE440 ephemeris, with no LLM. Every result is reproducible and SHA-256
verifiable. This is data for your own analysis, never a trading signal or a forecast.

```bash
pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"
```

The package is not on PyPI yet: install it from GitHub as above.

## Quick start

```python
from astro_agents import Client

client = Client()            # reads ASTRO_CREDITS_TOKEN; without one, each client gets 1 free call on the $0.01-0.02 routes

# Gann planetary lines as a time series: one column per line, indexed by UTC time
lines = client.planetary_lines(start="2024-01-01", end="2024-12-31",
                               bodies=["jupiter", "saturn"], averages=["mean_of_5"])
lines[["geo.jupiter", "helio.jupiter", "geo.mean_of_5"]].tail()

# Every eclipse, retrograde station and ingress over five years (paged year by year for you)
events = client.events(start="2020-01-01", end="2024-12-31", include=["eclipse", "station", "ingress"])
events[["time", "type", "body", "position"]].head()

# Heliocentric positions with right ascension and declination
client.positions("2024-03-01T00:00Z", perspective="heliocentric", coordinates="equatorial")

# Declination parallels
client.parallels("2024-03-01T00:00Z")

# Matching skies: past analogues of a date's slow-planet sky, one per passage (10 years apart)
past = client.analogues("2026-10-29T00:00Z", direction="past",
                        bodies=["jupiter", "saturn", "uranus", "neptune", "pluto"], min_separation_days=3650)
past[["time", "score", "geo.jupiter", "geo.saturn"]]
# ...and the next ones; or your own configuration, e.g. {"geo.jupiter-saturn:angle": 0}
future = client.analogues("2026-10-29T00:00Z", direction="future", min_separation_days=365)
```

`analogues()` ranks dates by a stated angular distance (`score`, in degrees; the formula is in
`df.attrs["metric"]`, and each row carries its `distance:<feature id>` columns). It finds matching positions,
nothing more: data for your own analysis — never a signal or forecast. See `examples/sky_analogues.py`.

Joining events onto candles takes one call, `merge_events`. It wraps `pandas.merge_asof` and first aligns the
time resolutions, which pandas 3 mixes:

```python
from astro_agents import merge_events
merged = merge_events(candles, events, on="open_time", tolerance="1D")   # latest event at or before each candle
```

## Paying

| Mode | How |
|---|---|
| Free | No token: 1 free call per client on the $0.01-0.02 routes (positions, aspects, sky, nakshatras, panchang, birth time). |
| Prepaid credits | `export ASTRO_CREDITS_TOKEN=astc_...`. The client sends it as `X-Credits-Token` on paid calls only, and never logs or prints it. |
| Buy credits | `pip install "astro-agents[x402]"`, then `client.buy_credits("backtest")`. The key comes from `$EVM_PRIVATE_KEY` (USDC on Base) and only signs locally. |

The packs:

| Pack | You pay | Credits | Bonus |
|---|---|---|---|
| Probe | $10 | 10 | none |
| Backtest | $50 | 60 | +20% |
| Quant | $200 | 260 | +30% |
| Autopilot | $1000 | 1400 | +40% |

1 credit = $1, and credits never expire. `client.packs()` lists the packs with what each one buys, and
`client.balance()` shows your balance. If a token leaks, `client.rotate_token()` replaces it.

Prices per call: positions $0.01, aspects $0.02, planetary lines $0.20, event calendar $0.25, sky analogues $0.25,
natal chart $0.06.
The full list is `client.catalog()`.

Long ranges are split into the calls the API accepts. A planetary-lines call holds up to 1000 samples; an events
call covers up to 366 days. `max_calls` (default 50) bounds how many paid calls one method may make.

## Verifying a result

```python
from astro_agents import verify_dataframe

verify_dataframe(lines)                      # offline: recompute every result_sha256 behind the DataFrame
lines.attrs["meta"]                          # input_sha256, result_sha256, engine, ephemeris...
res = client.natal(datetime="1990-05-15T14:30", latitude=48.8566, longitude=2.3522)
res.verify(), client.verify(res)             # offline, and by the API (POST /v1/verify, free)
```

Keep `input_sha256` and `result_sha256` with a backtest. The same request returns the same bytes, so the
backtest can be replayed and cited.

## Errors

| Exception | When |
|---|---|
| `PaymentRequiredError` (402) | No free call left, an always-paid route, or credits too low. It carries `price_usd`, `balance_usd`, `topup_url` and `packs`. |
| `InvalidTokenError` (401) | The token is unknown or revoked. Nothing is charged. |
| `InputError` (400) | Invalid input, with `code` and `field`. Never charged. |
| `RateLimitError` (429) | Raised after retries, with `retry_after`. |
| `ServerError`, `TransportError` | Server error, or no answer from the API. |

The client retries only what cannot have been charged: 429, 503, and requests that never left your machine. A
timeout on a paid call is not retried.

## All methods

- Finance: `planetary_lines`, `events`.
- Western: `positions`, `aspects`, `parallels`, `sky`, `natal`, `transits`, `synastry`.
- Vedic: `kundli`, `kundli_full`, `dashas`, `doshas`, `gun_milan`, `vedic_report`, `kp`, `yogas`, `panchang`,
  `nakshatras`.
- Time: `resolve_time`.
- Generic: `call(route, body)`.
- Free: `catalog`, `health`, `packs`, `verify`.

Chart methods take the API's own parameters (`datetime`, `latitude`, `longitude`, `options`...) and return a
`Result` with `.data` and `.meta`. Pass `raw=True` to a DataFrame method to get the `Result` instead.

## Examples

[`examples/`](https://github.com/aidatatools-dev/astro-agents-clients/tree/main/python/examples):

- a quickstart notebook;
- planetary lines in vectorbt and in backtrader;
- events merged onto OHLC candles;
- a minimal Freqtrade strategy.

API reference: [llms-full.txt](https://astro-agent.dev/llms-full.txt) · [OpenAPI](https://astro-agent.dev/openapi.json) ·
[Finance guide](https://github.com/aidatatools-dev/astro-agents-clients/blob/main/docs/FINANCE.md).
