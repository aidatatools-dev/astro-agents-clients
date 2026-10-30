# Changelog

## 0.4.0 — 2026-10-30

- `token_chart(launch_datetime=..., symbol=..., chain=..., address=...)`: a token's launch sky and the key
  astronomical dates ahead as a DataFrame; launch planets, aspects and the SVG card in `df.attrs`.
- `token_synastry(a=..., b=...)`: two launch skies compared by geometry (cross-aspects DataFrame, `geometry_score`
  and the SVG card in `df.attrs`). Launch times are given by the caller; on-chain resolution is not available yet.
  Data for your own analysis — never a signal or forecast.

## 0.1.0 — 2026-10-29

First release: pandas-first client for the Astro Agents API.
- `planetary_lines` and `events` return DataFrames and split long ranges into calls the API accepts.
- `positions`, `aspects` and `parallels` return DataFrames; every chart route has a method.
- Prepaid credits via `ASTRO_CREDITS_TOKEN`; `balance`, `rotate_token`, `packs`, `buy_credits` (x402 extra).
- Typed errors, safe retries, and offline (`verify_local`) or API (`verify`) hash verification.
