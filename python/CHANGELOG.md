# Changelog

## 0.1.0 — 2026-10-29

First release: pandas-first client for the Astro Agents API.
- `planetary_lines` and `events` return DataFrames and split long ranges into calls the API accepts.
- `positions`, `aspects` and `parallels` return DataFrames; every chart route has a method.
- Prepaid credits via `ASTRO_CREDITS_TOKEN`; `balance`, `rotate_token`, `packs`, `buy_credits` (x402 extra).
- Typed errors, safe retries, and offline (`verify_local`) or API (`verify`) hash verification.
