# Astro Agents: clients and integrations

Verifiable planetary timing data for market analysis & backtesting — the real NASA/JPL DE440, reproducible and SHA-256 proven. For traders, quants and agents.

Public, MIT-licensed tools for [Astro Agents](https://astro-agent.dev), the API that serves NASA/JPL DE440 planetary
data for market analysis and backtesting (plus Western and Vedic astrology), every result SHA-256 verifiable.
Data for your own analysis, never a trading signal or forecast.

| Folder | What |
|---|---|
| [`python/`](python) | Official Python client `astro-agents`: pandas DataFrames for planetary lines and the event calendar, prepaid credits, offline hash verification. Examples: notebook, vectorbt, backtrader, events on OHLC, Freqtrade. |
| [`tradingview/`](tradingview) | Free TradingView indicator **Celestial Events & Planetary Lines** (Pine Script v5): Gann lines geo + helio, exact DE440 ingresses, stations and eclipses 1990-2040. |
| [`docs/`](docs) | [Finance guide](docs/FINANCE.md) and [prepaid credits](docs/CREDITS.md). |

```bash
pip install "astro-agents @ git+https://github.com/aidatatools-dev/astro-agents-clients#subdirectory=python"
```

API: [astro-agent.dev/finance](https://astro-agent.dev/finance) · [examples with real outputs](https://astro-agent.dev/examples)
· [catalog and prices](https://astro-agent.dev/v1/catalog) · [full reference](https://astro-agent.dev/llms-full.txt)
· [accuracy vs NASA/JPL Horizons](https://astro-agent.dev/benchmark.md)

This repository is synced from the service's source; issues and pull requests are welcome here.
