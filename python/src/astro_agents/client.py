"""Python client for the Astro Agents API (https://astro-agent.dev), pandas-first.

    from astro_agents import Client
    client = Client()                      # reads ASTRO_CREDITS_TOKEN; without it, the free call applies
    lines = client.planetary_lines(start="2024-01-01", end="2024-12-31", bodies=["jupiter", "saturn"])
    events = client.events(start="2020-01-01", end="2024-12-31", include=["eclipse", "station"])

Every response is deterministic and hashed: DataFrames carry the response `meta` (input_sha256,
result_sha256) in `df.attrs`, and `Client.verify` / `verify_local` recompute the hash.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable

import pandas as pd

from . import __version__
from ._hash import result_sha256
from .errors import (AstroAgentsError, InputError, InvalidTokenError, PaymentRequiredError, RateLimitError,
                     ServerError, TransportError, VerificationError)

DEFAULT_BASE_URL = "https://astro-agent.dev"
TOKEN_ENV = "ASTRO_CREDITS_TOKEN"
BASE_URL_ENV = "ASTRO_AGENTS_BASE_URL"
TOKEN_HEADER = "X-Credits-Token"
MAX_SERIES_SAMPLES = 1000          # per planetary-lines call (server limit)
MAX_EVENT_DAYS = 366               # per events call (server limit)
_SAMPLES_PER_DAY = {"1h": 24, "4h": 6, "12h": 2, "1d": 1}
_RETRY_STATUSES = (429, 503)       # answered without charging: safe to repeat

Transport = Callable[[str, str, dict, "bytes | None", float], "tuple[int, dict, bytes]"]


def _urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read()


class _NotSent(Exception):
    """The request never left this machine (DNS failure, connection refused): safe to retry."""


def _classify_network_error(exc: BaseException) -> BaseException:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (ConnectionRefusedError, socket.gaierror)):
        return _NotSent(str(reason))
    return exc


@dataclass
class Result:
    """One API response: `data` is the response's `result`, `meta` its provenance."""
    endpoint: str
    data: dict
    meta: dict = field(default_factory=dict)

    @property
    def input_sha256(self) -> str | None:
        return self.meta.get("input_sha256")

    @property
    def result_sha256(self) -> str | None:
        return self.meta.get("result_sha256")

    @property
    def payment(self) -> dict:
        return self.meta.get("payment") or {}

    def verify(self) -> bool:
        """Recompute result_sha256 locally (no network)."""
        return verify_local(self.data, self.result_sha256)

    def __getitem__(self, key):
        return self.data[key]


def verify_local(result: Any, expected_sha256: str | None) -> bool:
    """True when `result` hashes to `expected_sha256` under the service's rule."""
    if isinstance(result, Result):
        result, expected_sha256 = result.data, expected_sha256 or result.result_sha256
    return bool(expected_sha256) and result_sha256(result) == expected_sha256.lower()


def _d(value) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat() if value.tzinfo else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_day(value) -> date:
    try:
        return date.fromisoformat(_d(value)[:10])
    except ValueError:
        raise InputError(f"dates must be YYYY-MM-DD, got {value!r}", code="INVALID_DATE") from None


def _iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return value.isoformat(timespec="minutes")
    return str(value)


def _clean(body: dict) -> dict:
    return {k: v for k, v in body.items() if v is not None}


class Client:
    """Astro Agents API client.

    token        prepaid credits token (default: $ASTRO_CREDITS_TOKEN). Sent as X-Credits-Token on paid
                 calls only. Without a token, each client gets one free call on the $0.01-0.02 routes;
                 any other call raises PaymentRequiredError with how to pay.
    base_url     default https://astro-agent.dev ($ASTRO_AGENTS_BASE_URL).
    timeout      seconds per request.
    max_retries  retries for answers that charge nothing (429, 503) and for requests that never left
                 (DNS, connection refused). A timeout is never retried on a paid call: it may have
                 been charged.
    max_calls    upper bound of API calls one paginated method may make (planetary_lines and events
                 split long ranges into several paid calls).
    """

    def __init__(self, token: str | None = None, base_url: str | None = None, timeout: float = 60.0,
                 max_retries: int = 3, backoff: float = 0.5, max_calls: int = 50, skip_free_call: bool = False,
                 transport: Transport | None = None):
        self._token = token if token is not None else (os.environ.get(TOKEN_ENV) or None)
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
        self.timeout, self.max_retries, self.backoff, self.max_calls = timeout, max_retries, backoff, max_calls
        self.skip_free_call = skip_free_call
        self._transport = transport or _urllib_transport
        self._sleep = time.sleep

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r}, token={'set' if self._token else 'none'})"

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    # --- HTTP -------------------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None, *, paid: bool = False,
                 extra_headers: dict | None = None, retries: int | None = None):
        headers = {"Accept": "application/json", "User-Agent": f"astro-agents-python/{__version__}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if paid and self._token:
            headers[TOKEN_HEADER] = self._token
        if paid and self.skip_free_call and not self._token:
            headers["X-Free-Call"] = "skip"
        headers.update(extra_headers or {})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        url = self.base_url + path
        attempts = (self.max_retries if retries is None else retries) + 1
        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                status, rheaders, raw = self._transport(method, url, headers, data, self.timeout)
            except Exception as exc:  # noqa: BLE001
                exc = _classify_network_error(exc)
                if isinstance(exc, _NotSent) and not last:
                    self._sleep(self.backoff * 2 ** attempt)
                    continue
                if isinstance(exc, _NotSent):
                    raise TransportError(f"could not reach {self.base_url}: {exc}") from None
                raise TransportError(f"no answer from {url}: {type(exc).__name__}"
                                     + (" (a paid call may have been charged; check GET /v1/credits/balance)"
                                        if paid and self._token else "")) from None
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                payload = {"error": raw[:200].decode("utf-8", "replace")}
            if status in _RETRY_STATUSES and not last:
                wait = self.backoff * 2 ** attempt
                if status == 429:
                    try:
                        wait = min(float(rheaders.get("retry-after", wait)), 30.0)
                    except ValueError:
                        pass
                self._sleep(wait)
                continue
            if 200 <= status < 300:
                return payload, rheaders
            raise self._error(status, payload, rheaders)
        raise AssertionError("unreachable")

    @staticmethod
    def _error(status: int, body: dict, headers: dict) -> AstroAgentsError:
        body = body if isinstance(body, dict) else {"error": str(body)}
        msg = body.get("error") or f"HTTP {status}"
        code = body.get("code")
        if status == 400 or status == 413:
            return InputError(msg, status, code, body)
        if status == 401:
            return InvalidTokenError(msg, status, code or "CREDITS_TOKEN_INVALID", body)
        if status == 402:
            if not body.get("price_usd") and headers.get("x-price-usd"):
                body = {**body, "price_usd": headers["x-price-usd"]}
            return PaymentRequiredError(msg, status, code or "PAYMENT_REQUIRED", body)
        if status == 429:
            try:
                retry_after = float(headers.get("retry-after", "") or body.get("retry_after_s"))
            except (TypeError, ValueError):
                retry_after = None
            return RateLimitError(msg, status, code or "RATE_LIMITED", body, retry_after=retry_after)
        if status >= 500:
            return ServerError(msg, status, code, body)
        return AstroAgentsError(msg, status, code, body)

    # --- generic -----------------------------------------------------------------------------

    def call(self, route: str, body: dict | None = None, **params) -> Result:
        """POST /v1/<route> with `body` (or keyword parameters). Returns a Result."""
        payload, _ = self._request("POST", f"/v1/{route.strip('/')}", _clean({**(body or {}), **params}), paid=True)
        return Result(payload.get("endpoint", route), payload.get("result") or {}, payload.get("meta") or {})

    def catalog(self) -> dict:
        """Everything for sale: routes, prices, schemas, credit packs. Free."""
        return self._request("GET", "/v1/catalog")[0]

    def health(self) -> dict:
        return self._request("GET", "/v1/health")[0]

    def verify(self, result: Any, result_sha256: str | None = None) -> bool:
        """Ask the API to recompute a result's hash (POST /v1/verify, free; no token is sent)."""
        if isinstance(result, Result):
            result, result_sha256 = result.data, result_sha256 or result.result_sha256
        if isinstance(result, pd.DataFrame):
            raise InputError("verify() takes the Result (client.call / raw=True), not a DataFrame",
                             code="INVALID_RESULT")
        out, _ = self._request("POST", "/v1/verify", {"result": result, "result_sha256": result_sha256})
        if result_sha256 is None:
            return bool(out.get("result_sha256"))
        return bool(out.get("matches"))

    # --- finance -------------------------------------------------------------------------------

    def planetary_lines(self, datetime: str | None = None, *, start=None, end=None, interval: str = "1d",
                        bodies: Iterable[str] | None = None, perspective: str | None = None,
                        aspects=None, averages: Iterable[str] | None = None, average_method: str | None = None,
                        price_unit: float | None = None, price_range: dict | None = None,
                        unwrap: bool | None = None, include_declination: bool | None = None,
                        time_utc: str | None = None, options: dict | None = None,
                        raw: bool = False) -> pd.DataFrame | Result:
        """Gann planetary lines ($0.20 per call).

        Series (start + end, YYYY-MM-DD, inclusive): a DataFrame indexed by UTC time with one column
        per line (`geo.jupiter`, `helio.mean_of_5+90`, ...) and a `timestamp` column (unix seconds).
        Ranges over 1000 samples are split into several calls (bounded by `max_calls`).
        Snapshot (`datetime`): a DataFrame of lines indexed by line id; with `price_unit`,
        `pd.DataFrame(df.attrs["price_levels"])` gives the price levels.
        """
        common = _clean({"interval": interval, "bodies": list(bodies) if bodies else None,
                         "perspective": perspective, "aspects": aspects,
                         "averages": list(averages) if averages else None, "average_method": average_method,
                         "price_unit": price_unit, "price_range": price_range, "unwrap": unwrap,
                         "include_declination": include_declination, "time_utc": time_utc, "options": options})
        if datetime is not None:
            if start is not None or end is not None:
                raise InputError("give either datetime (snapshot) or start + end (series)", code="INVALID_RANGE")
            common.pop("interval", None)
            common.pop("time_utc", None)
            res = self.call("finance/planetary-lines", {**common, "datetime": _iso(datetime)})
            if raw:
                return res
            df = pd.DataFrame(res["lines"])
            if not df.empty:
                df = df.set_index("id")
            df.attrs.update(meta=res.meta, result_sha256=res.result_sha256, settings=res.data.get("settings"),
                            price_levels=res.data.get("price_levels") or [])
            return df
        if start is None or end is None:
            raise InputError("planetary_lines needs datetime, or start and end", code="INVALID_RANGE")
        chunks = self._series_chunks(_parse_day(start), _parse_day(end), interval)
        results = [self.call("finance/planetary-lines", {**common, "start": a.isoformat(), "end": b.isoformat(),
                                                          "format": "columns"}) for a, b in chunks]
        if raw:
            return results[0] if len(results) == 1 else results
        df = pd.concat([pd.DataFrame(r["series"]) for r in results], ignore_index=True)
        if not df.empty:
            df = df.drop_duplicates("timestamp").sort_values("timestamp")
            df.index = _utc(df["timestamp"])
            df.index.name = "time"
        _attach(df, results)
        return df

    def _series_chunks(self, start: date, end: date, interval: str) -> list[tuple[date, date]]:
        if end < start:
            raise InputError("'end' must not be before 'start'", code="INVALID_RANGE")
        if interval == "1w":
            span = timedelta(weeks=MAX_SERIES_SAMPLES)
        elif interval in _SAMPLES_PER_DAY:
            span = timedelta(days=MAX_SERIES_SAMPLES // _SAMPLES_PER_DAY[interval])
        else:
            raise InputError(f"interval must be one of 1h, 4h, 12h, 1d, 1w, got {interval!r}", code="INVALID_INTERVAL")
        return self._split(start, end, span)

    def _split(self, start: date, end: date, span: timedelta) -> list[tuple[date, date]]:
        chunks, a = [], start
        while a <= end:
            b = min(end, a + span - timedelta(days=1))
            chunks.append((a, b))
            a = b + timedelta(days=1)
        if len(chunks) > self.max_calls:
            raise InputError(f"this range needs {len(chunks)} paid calls, more than max_calls={self.max_calls}; "
                             "raise max_calls or use a longer interval", code="TOO_MANY_CALLS")
        return chunks

    def events(self, start, end, *, include: Iterable[str] | None = None, bodies: Iterable[str] | None = None,
               perspective: str | None = None, include_moon: bool | None = None, aspects=None,
               options: dict | None = None, raw: bool = False) -> pd.DataFrame | Result:
        """Celestial event calendar ($0.25 per call): ingresses, stations, lunations, eclipses, aspects,
        declination parallels, out-of-bounds, each to the UTC minute.

        Returns a DataFrame sorted by time, with `time` (UTC datetime), `timestamp` (unix seconds),
        `type`, `key` and the event's fields. Ranges over 366 days are split year by year (bounded by
        `max_calls`) and de-duplicated on `key`.
        """
        common = _clean({"include": list(include) if include else None, "bodies": list(bodies) if bodies else None,
                         "perspective": perspective, "include_moon": include_moon, "aspects": aspects,
                         "options": options})
        chunks = self._split(_parse_day(start), _parse_day(end), timedelta(days=MAX_EVENT_DAYS))
        results = [self.call("finance/events", {**common, "start": a.isoformat(), "end": b.isoformat()})
                   for a, b in chunks]
        if raw:
            return results[0] if len(results) == 1 else results
        rows = [e for r in results for e in r["events"]]
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.drop_duplicates("key").sort_values(["timestamp", "key"]).reset_index(drop=True)
            df.insert(0, "time", _utc(df["timestamp"]))
        _attach(df, results)
        return df

    # --- western -----------------------------------------------------------------------------------

    def positions(self, datetime=None, latitude: float | None = None, longitude: float | None = None, *,
                  perspective: str | None = None, coordinates: str | None = None, zodiac: str | None = None,
                  ayanamsa: str | None = None, points=None, options: dict | None = None, raw: bool = False,
                  **params) -> pd.DataFrame | Result:
        """Planet positions ($0.01): a DataFrame indexed by point. `perspective="heliocentric"`,
        `coordinates="equatorial"` (adds right ascension, declination, out_of_bounds columns)."""
        opts = _clean({**(options or {}), "perspective": perspective, "coordinates": coordinates,
                       "zodiac": zodiac, "ayanamsa": ayanamsa, "points": points})
        res = self.call("western/positions", _clean({"datetime": _iso(datetime) if datetime is not None else None,
                                                     "latitude": latitude, "longitude": longitude,
                                                     "options": opts or None, **params}))
        if raw:
            return res
        df = pd.json_normalize(res["points"], sep="_")
        df.columns = [c.replace("equatorial_", "") for c in df.columns]
        if not df.empty:
            df = df.set_index("point")
        _attach(df, [res])
        return df

    def aspects(self, datetime=None, latitude: float | None = None, longitude: float | None = None, *,
                declination: bool | None = None, declination_orb: float | None = None, longitudes: dict | None = None,
                options: dict | None = None, raw: bool = False, **params) -> pd.DataFrame | Result:
        """Aspects ($0.02): a DataFrame of aspects. With `declination=True`, parallels and
        contra-parallels are in `df.attrs["declination_aspects"]` (a list; `parallels()` gives a DataFrame)."""
        opts = _clean({**(options or {}), "declination": declination, "declination_orb": declination_orb})
        res = self.call("western/aspects", _clean({"datetime": _iso(datetime) if datetime is not None else None,
                                                   "latitude": latitude, "longitude": longitude,
                                                   "longitudes": longitudes, "options": opts or None, **params}))
        if raw:
            return res
        df = pd.DataFrame(res.data.get("aspects") or [])
        _attach(df, [res])
        df.attrs["declination_aspects"] = res.data.get("declination_aspects") or []
        df.attrs["declinations"] = res.data.get("declinations")
        return df

    def parallels(self, datetime=None, latitude=None, longitude=None, *, declination_orb: float | None = None,
                  **params) -> pd.DataFrame:
        """Declination parallels and contra-parallels ($0.02, one aspects call)."""
        df = self.aspects(datetime, latitude, longitude, declination=True, declination_orb=declination_orb, **params)
        out = pd.DataFrame(df.attrs["declination_aspects"])
        out.attrs.update(meta=df.attrs["meta"], result_sha256=df.attrs["result_sha256"])
        return out

    def sky(self, datetime=None, days: int | None = None, **params) -> Result:
        """The sky now and the next 1-90 days of events ($0.01)."""
        return self.call("western/sky", _clean({"datetime": _iso(datetime) if datetime is not None else None,
                                                "days": days, **params}))

    # --- charts: one method per route, keyword parameters as in the API ------------------------------

    def resolve_time(self, **params) -> Result:
        return self.call("time/resolve", params)

    def natal(self, **params) -> Result:
        return self.call("western/natal", params)

    def transits(self, **params) -> Result:
        return self.call("western/transits", params)

    def synastry(self, **params) -> Result:
        return self.call("western/synastry", params)

    def nakshatras(self, **params) -> Result:
        return self.call("vedic/nakshatra", params)

    def panchang(self, **params) -> Result:
        return self.call("vedic/panchang", params)

    def kundli(self, **params) -> Result:
        return self.call("vedic/kundli", params)

    def kundli_full(self, **params) -> Result:
        return self.call("vedic/kundli-full", params)

    def dashas(self, **params) -> Result:
        return self.call("vedic/dashas", params)

    def doshas(self, **params) -> Result:
        return self.call("vedic/doshas", params)

    def gun_milan(self, **params) -> Result:
        return self.call("vedic/gun-milan", params)

    def vedic_report(self, **params) -> Result:
        return self.call("vedic/report", params)

    def kp(self, **params) -> Result:
        return self.call("vedic/kp", params)

    def yogas(self, **params) -> Result:
        return self.call("vedic/yogas", params)

    # --- prepaid credits ------------------------------------------------------------------------------

    def balance(self) -> dict:
        """The credits balance and recent movements of the current token."""
        if not self._token:
            raise InvalidTokenError(f"no credits token: set {TOKEN_ENV} or pass token=", code="NO_TOKEN")
        return self._request("GET", "/v1/credits/balance", extra_headers={TOKEN_HEADER: self._token})[0]

    def rotate_token(self) -> str:
        """Replace the token (the old one stops working at once). The client switches to the new one,
        which is returned: store it."""
        if not self._token:
            raise InvalidTokenError(f"no credits token: set {TOKEN_ENV} or pass token=", code="NO_TOKEN")
        out, _ = self._request("POST", "/v1/credits/rotate", {}, extra_headers={TOKEN_HEADER: self._token},
                               retries=0)
        self._token = out["token"]
        return out["token"]

    def packs(self) -> pd.DataFrame:
        """The credit packs (Probe, Backtest, Quant, Autopilot) with their value. Free."""
        return pd.DataFrame(self._request("GET", "/v1/credits")[0]["packs"]).set_index("id")

    def buy_credits(self, pack: str, private_key: str | None = None, network: str = "eip155:8453") -> dict:
        """Buy a credit pack with x402 (USDC on Base by default), then use the new balance.

        Needs `pip install "astro-agents[x402]"` and an EVM key (argument or $EVM_PRIVATE_KEY); the key
        only signs locally. With a token already set, the pack tops up the same balance. The new
        token (first purchase) is set on the client and returned in the answer: store it, it is shown
        once. The payment request is never retried."""
        key = private_key or os.environ.get("EVM_PRIVATE_KEY")
        if not key:
            raise InputError("buy_credits needs an EVM private key (private_key= or $EVM_PRIVATE_KEY)",
                             code="NO_SIGNER")
        try:
            from eth_account import Account
            from x402 import x402ClientSync
            from x402.http import decode_payment_required_header, encode_payment_signature_header
            from x402.mechanisms.evm.exact.register import register_exact_evm_client
            from x402.mechanisms.evm.signers import EthAccountSigner
        except ImportError:
            raise AstroAgentsError('buy_credits needs the x402 extra: pip install "astro-agents[x402]"') from None
        body = {"pack": pack}
        auth = {TOKEN_HEADER: self._token} if self._token else {}
        required = decode_payment_required_header(self._payment_offer(body, auth))
        required.accepts = [a for a in required.accepts if a.network == network]
        if not required.accepts:
            raise AstroAgentsError(f"the top-up offers no {network} payment")
        signer = x402ClientSync()
        register_exact_evm_client(signer, EthAccountSigner(Account.from_key(key)), networks=network)
        price = max(int(a.amount) for a in required.accepts) / 1_000_000
        signer.set_spend_controls({"max_amount_per_payment": f"${price:.2f}"})
        signature = encode_payment_signature_header(signer.create_payment_payload(required))
        out, _ = self._request("POST", "/v1/credits/topup", body, retries=0,
                               extra_headers={**auth, "PAYMENT-SIGNATURE": signature})
        if out.get("token"):
            self._token = out["token"]
        return out

    def _payment_offer(self, body: dict, auth: dict) -> str:
        """The x402 offer (PAYMENT-REQUIRED) of an unpaid top-up request."""
        status, headers, _ = self._transport("POST", self.base_url + "/v1/credits/topup",
                                             {"Content-Type": "application/json",
                                              "User-Agent": f"astro-agents-python/{__version__}", **auth},
                                             json.dumps(body).encode(), self.timeout)
        header = headers.get("payment-required")
        if status != 402 or not header:
            raise AstroAgentsError("the top-up answered without an x402 offer")
        return header


def _utc(seconds) -> pd.Series:
    """Unix seconds -> UTC datetimes in nanoseconds, the same dtype on pandas 1.x, 2.x and 3.x."""
    return pd.to_datetime(seconds, unit="s", utc=True).astype("datetime64[ns, UTC]")


def merge_events(candles: pd.DataFrame, events: pd.DataFrame, on: str = "open_time", tolerance="1D",
                 columns=("type", "body", "key"), direction: str = "backward") -> pd.DataFrame:
    """Attach to each candle the latest event at or before its time (within `tolerance`), with
    pandas.merge_asof. The time columns are aligned to the same resolution first (pandas 3 mixes
    seconds, microseconds and nanoseconds), and both sides are sorted."""
    left = candles.copy()
    left[on] = pd.to_datetime(left[on], utc=True)
    right = events[["time", *[c for c in columns if c in events.columns]]].copy()
    right["time"] = right["time"].astype(left[on].dtype)
    out = pd.merge_asof(left.sort_values(on), right.sort_values("time"), left_on=on, right_on="time",
                        direction=direction, tolerance=pd.Timedelta(tolerance) if tolerance is not None else None)
    return out.rename(columns={"time": "event_time"})


def _attach(df: pd.DataFrame, results: list[Result]) -> None:
    metas = [r.meta for r in results]
    df.attrs["meta"] = metas[0] if len(metas) == 1 else metas
    df.attrs["result_sha256"] = metas[0].get("result_sha256") if len(metas) == 1 else [m.get("result_sha256")
                                                                                     for m in metas]
    df.attrs["calls"] = len(results)
    df.attrs["results"] = results


def verify_dataframe(df: pd.DataFrame) -> bool:
    """Recompute, offline, the hash of every API result behind a DataFrame returned by the client."""
    results = df.attrs.get("results") or []
    if not results:
        raise VerificationError("this DataFrame carries no API result to verify")
    return all(r.verify() for r in results)
