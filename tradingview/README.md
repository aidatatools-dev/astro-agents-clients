# Celestial Events & Planetary Lines (TradingView, free)

An open-source Pine Script v5 indicator for TradingView: Gann planetary lines (geocentric and heliocentric) on the price
scale, plus sign ingresses, stations and eclipses marked on the chart. Data for your own analysis, never a trading
signal or forecast.

- **Script:** [`celestial_events_planetary_lines.pine`](celestial_events_planetary_lines.pine). Paste it into the Pine
  Editor and click "Add to chart".
- **Events are exact.** The table holds 3,666 events from 1990 to 2040: every geocentric sign ingress and station from
  the Sun to Pluto, and every solar and lunar eclipse with its type. Each one is timed to the UTC minute by the
  [Astro Agents](https://astro-agent.dev) DE440 engine, the same output as
  [`POST /v1/finance/events`](https://astro-agent.dev/finance).
- **Lines are approximate, and the error is measured.** Pine Script cannot load an ephemeris, so the indicator computes
  longitudes from JPL's Keplerian elements (Standish, Table 1), with precession, nutation and light-time.
  A line-by-line Python port of that math is compared with the DE440 engine (the script lives with the engine).
  Maximum error on a 5-day grid, 1990-2040:

  | Body | Max error | Body | Max error |
  |---|---|---|---|
  | Sun / Earth | < 1′ | Jupiter | 5′ |
  | Mercury | 1′ | Saturn | 11′ |
  | Venus | 2′ | Uranus | 2′ |
  | Mars | 4′ | Neptune, Pluto | 1′ |

  For exact lines at any interval, use [`POST /v1/finance/planetary-lines`](https://astro-agent.dev/finance). It is
  DE440 and SHA-256 proven, and the [Python client](../python) returns DataFrames.

## What it draws

- **Planetary lines:** for each selected body (or the Mean of 5 and Circle of 8 averages), the two harmonics nearest
  to price, using `price = (degree + step × k) × price per degree`.
  - The step can be 360° (one line per turn), 180°, 120°, 90°, 60°, 45° or 30°.
  - Geocentric lines are solid, heliocentric ones dotted. A one-bar gap marks the moment price crosses a line.
  - The lines are projected forward as dotted or dashed polylines, for up to 365 days (and at most 490 bars).
- **Events:** a label per bar showing the glyphs (☉→♈, ♃ ℞, ☿ D, ☉ eclipse). Its tooltip gives the exact UTC
  minute. Markers below the bars stay visible over the whole history.
  - Upcoming events inside the projection window are placed at their exact future time.
- **Positions table:** the geocentric and heliocentric longitude of every body, with ℞ when retrograde.

The inputs are price per degree (0 picks a power of ten from the price), the step, geocentric and/or heliocentric
lines, the bodies, the event types, and whether to show events for every body or only the selected ones.

## Source of truth

The `.pine` file is generated with its event table from the Astro Agents engine; changes are made there and synced here.

## Publishing

The indicator is published on TradingView as an open-source script under the same name.

MIT License.
