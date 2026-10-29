"""Client tests against a mocked API (no network)."""
from __future__ import annotations

import json
import socket
import urllib.error

import pandas as pd
import pytest

from astro_agents import (Client, InputError, InvalidTokenError, PaymentRequiredError, RateLimitError, Result,
                          ServerError, TransportError, result_sha256, verify_dataframe, verify_local)
from astro_agents.client import TOKEN_HEADER

TOKEN = "astc_" + "x" * 43


class FakeAPI:
    """Records requests; answers with the queued (status, body, headers) or a handler."""

    def __init__(self, handler=None):
        self.requests = []
        self.queue = []
        self.handler = handler

    def __call__(self, method, url, headers, body, timeout):
        req = {"method": method, "url": url, "headers": dict(headers),
               "body": json.loads(body) if body else None, "timeout": timeout}
        self.requests.append(req)
        if self.queue:
            item = self.queue.pop(0)
            if isinstance(item, BaseException):
                raise item
            status, payload, rh = (item + ({},))[:3]
        else:
            status, payload, rh = (tuple(self.handler(req)) + ({},))[:3]
        return status, {k.lower(): v for k, v in rh.items()}, json.dumps(payload).encode()


def envelope(endpoint, result):
    return {"endpoint": endpoint, "result": result,
            "meta": {"input_sha256": "i" * 64, "result_sha256": result_sha256(result), "engine": "astro-agents/1.5.0",
                     "payment": {"protocol": "credits"}}}


def client(api, **kw):
    c = Client(token=kw.pop("token", TOKEN), base_url="https://api.test", transport=api, **kw)
    c._sleep = lambda s: api.requests.append({"slept": s})
    return c


# --- auth -----------------------------------------------------------------------------------------

def test_token_from_env_sent_only_on_paid_calls_and_never_shown(monkeypatch):
    monkeypatch.setenv("ASTRO_CREDITS_TOKEN", TOKEN)
    api = FakeAPI(lambda r: (200, envelope("western/positions", {"points": [{"point": "sun", "longitude": 1.5}]})))
    c = Client(base_url="https://api.test", transport=api)
    assert TOKEN not in repr(c) and c.has_token
    c.positions("2024-01-01T00:00Z")
    assert api.requests[0]["headers"][TOKEN_HEADER] == TOKEN
    api.handler = lambda r: (200, {"result_sha256": "a", "matches": True})
    c.verify({"a": 1}, "a")
    assert TOKEN_HEADER not in api.requests[-1]["headers"]          # free endpoint: no token


def test_no_token_mode_sends_no_header(monkeypatch):
    monkeypatch.delenv("ASTRO_CREDITS_TOKEN", raising=False)
    api = FakeAPI(lambda r: (200, envelope("western/positions", {"points": []})))
    Client(base_url="https://api.test", transport=api).positions("2024-01-01T00:00Z")
    assert TOKEN_HEADER not in api.requests[0]["headers"]


# --- errors ---------------------------------------------------------------------------------------

def test_402_carries_price_balance_and_topup():
    api = FakeAPI()
    api.queue.append((402, {"error": "insufficient credits", "code": "CREDITS_INSUFFICIENT", "price_usd": "0.200000",
                            "balance_usd": "0.100000", "topup": "https://astro-agent.dev/v1/credits/topup",
                            "packs": [{"id": "probe"}]}))
    with pytest.raises(PaymentRequiredError) as e:
        client(api).planetary_lines("2024-01-01T00:00Z")
    assert e.value.code == "CREDITS_INSUFFICIENT" and e.value.price_usd == "0.200000"
    assert e.value.balance_usd == "0.100000" and e.value.topup_url.endswith("/topup") and e.value.packs
    assert len(api.requests) == 1                                   # a 402 is never retried


def test_401_and_400_are_typed_and_not_retried():
    api = FakeAPI()
    api.queue += [(401, {"error": "invalid or revoked credits token", "code": "CREDITS_TOKEN_INVALID"}),
                  (400, {"error": "'start' must be YYYY-MM-DD", "code": "INVALID_DATE", "field": "start"})]
    c = client(api)
    with pytest.raises(InvalidTokenError):
        c.positions("2024-01-01T00:00Z")
    with pytest.raises(InputError) as e:
        c.events("2024-01-01", "2024-01-02")
    assert e.value.field == "start" and len(api.requests) == 2


def test_429_and_503_are_retried_then_raised():
    api = FakeAPI()
    api.queue += [(429, {"error": "slow down"}, {"Retry-After": "2"}),
                  (503, {"error": "credits unavailable", "code": "CREDITS_UNAVAILABLE"}),
                  (200, envelope("western/positions", {"points": []}))]
    c = client(api)
    c.positions("2024-01-01T00:00Z")
    sleeps = [r["slept"] for r in api.requests if "slept" in r]
    assert sleeps[0] == 2.0 and len(sleeps) == 2
    api.queue += [(429, {"error": "slow down"}, {"Retry-After": "1"})] * 4
    with pytest.raises(RateLimitError) as e:
        c.positions("2024-01-01T00:00Z")
    assert e.value.retry_after == 1.0


def test_500_is_not_retried():
    api = FakeAPI()
    api.queue.append((500, {"error": "internal error: KeyError"}))
    with pytest.raises(ServerError):
        client(api).positions("2024-01-01T00:00Z")
    assert len(api.requests) == 1


def test_only_unsent_requests_are_retried_after_network_errors():
    api = FakeAPI()
    api.queue += [urllib.error.URLError(ConnectionRefusedError()), (200, envelope("western/positions", {"points": []}))]
    client(api).positions("2024-01-01T00:00Z")                      # refused: never sent, retried
    api = FakeAPI()
    api.queue += [socket.timeout("timed out"), (200, envelope("western/positions", {"points": []}))]
    with pytest.raises(TransportError) as e:
        client(api).positions("2024-01-01T00:00Z")                  # timeout on a paid call: may be charged
    assert "may have been charged" in str(e.value)
    assert sum("url" in r for r in api.requests) == 1


# --- DataFrames and pagination -------------------------------------------------------------------

def series_handler(req):
    from datetime import date, timedelta
    b = req["body"]
    d0, d1 = date.fromisoformat(b["start"]), date.fromisoformat(b["end"])
    days = [(d0 + timedelta(days=i)) for i in range((d1 - d0).days + 1)]
    ts = [int(pd.Timestamp(d, tz="UTC").timestamp()) for d in days]
    return 200, envelope("finance/planetary-lines", {"series": {
        "time_utc": [f"{d}T00:00Z" for d in days], "timestamp": ts, "geo.jupiter": [10.0 + i for i in range(len(ts))]}})


def test_planetary_lines_series_is_paged_and_indexed_by_time():
    api = FakeAPI(series_handler)
    df = client(api).planetary_lines(start="2020-01-01", end="2023-12-31", bodies=["jupiter"])
    bodies = [r["body"] for r in api.requests if "body" in r]
    assert [(b["start"], b["end"]) for b in bodies] == [("2020-01-01", "2022-09-26"), ("2022-09-27", "2023-12-31")]
    assert all(b["format"] == "columns" and b["bodies"] == ["jupiter"] for b in bodies)
    assert len(df) == 1461 and df.index.is_monotonic_increasing and str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("2020-01-01", tz="UTC") and df.attrs["calls"] == 2
    assert verify_dataframe(df)


def test_hourly_series_chunks_stay_under_1000_samples():
    c = client(FakeAPI())
    chunks = c._series_chunks(pd.Timestamp("2024-01-01").date(), pd.Timestamp("2024-03-31").date(), "1h")
    assert all(((b - a).days + 1) * 24 <= 1000 for a, b in chunks) and chunks[0][0].isoformat() == "2024-01-01"


def test_max_calls_bounds_spending():
    with pytest.raises(InputError) as e:
        client(FakeAPI(series_handler), max_calls=3).planetary_lines(start="2024-01-01", end="2024-12-31",
                                                                      interval="1h")
    assert e.value.code == "TOO_MANY_CALLS"


def test_events_are_paged_by_366_days_deduplicated_and_sorted():
    def handler(req):
        b = req["body"]
        ev = [{"type": "station", "body": "mercury", "exact_utc": "2024-04-01T22:14Z", "timestamp": 1712009640,
               "key": "station:mercury:retrograde:2024-04-01T22:14Z"},
              {"type": "eclipse", "kind": "solar", "exact_utc": b["start"] + "T12:00Z",
               "timestamp": int(pd.Timestamp(b["start"] + "T12:00Z").timestamp()), "key": "eclipse:" + b["start"]}]
        return 200, envelope("finance/events", {"events": ev})
    api = FakeAPI(handler)
    df = client(api).events("2023-01-01", "2024-12-31", include=["station", "eclipse"])
    bodies = [r["body"] for r in api.requests if "body" in r]
    assert [(b["start"], b["end"]) for b in bodies] == [("2023-01-01", "2024-01-01"), ("2024-01-02", "2024-12-31")]
    assert df["key"].is_unique and df["time"].is_monotonic_increasing and len(df) == 3
    assert str(df["time"].dt.tz) == "UTC"


def test_positions_flatten_equatorial_and_aspects_parallels():
    api = FakeAPI()
    api.queue.append((200, envelope("western/positions", {"points": [
        {"point": "mars", "longitude": 290.6, "equatorial": {"right_ascension": 292.1, "declination": -22.9,
                                                              "out_of_bounds": False}}]})))
    df = client(api).positions("2024-01-01T00:00Z", perspective="heliocentric", coordinates="equatorial")
    assert api.requests[0]["body"]["options"] == {"perspective": "heliocentric", "coordinates": "equatorial"}
    assert df.loc["mars", "declination"] == -22.9 and "right_ascension" in df.columns
    api.queue.append((200, envelope("western/aspects", {"aspects": [], "declination_aspects": [
        {"point_a": "sun", "point_b": "pluto", "aspect": "parallel", "orb": 0.07}]})))
    par = client(api).parallels("2024-01-01T00:00Z")
    assert api.requests[-1]["body"]["options"] == {"declination": True}
    assert par.iloc[0]["aspect"] == "parallel" and par.attrs["result_sha256"]


def test_snapshot_lines_and_concat_with_attrs():
    api = FakeAPI()
    api.queue.append((200, envelope("finance/planetary-lines", {"lines": [{"id": "geo.jupiter", "degree": 35.58}],
                                                                "price_levels": [{"price": 35.58, "line": "geo.jupiter"}]})))
    df = client(api).planetary_lines("2024-01-01T00:00Z", price_unit=1.0)
    assert "interval" not in api.requests[0]["body"] and df.loc["geo.jupiter", "degree"] == 35.58
    assert pd.DataFrame(df.attrs["price_levels"]).iloc[0]["price"] == 35.58
    pd.concat([df, df])                                             # attrs hold no DataFrame: concat works


# --- verification and credits ------------------------------------------------------------------------

def test_verify_local_matches_the_service_rule():
    result = {"b": 1, "a": [0.1234567, -0.0000001, float("nan"), True, None, "x"]}
    canonical = '{"a":[0.123457,0.0,null,true,null,"x"],"b":1}'
    import hashlib
    assert result_sha256(result) == hashlib.sha256(canonical.encode()).hexdigest()
    assert verify_local(result, result_sha256(result)) and not verify_local(result, "0" * 64)
    res = Result("x", result, {"result_sha256": result_sha256(result)})
    assert res.verify()


def test_rotate_switches_the_client_to_the_new_token():
    api = FakeAPI()
    new = "astc_" + "y" * 43
    api.queue.append((200, {"account": "a", "token": new}))
    c = client(api)
    assert c.rotate_token() == new and c._token == new
    assert api.requests[0]["headers"][TOKEN_HEADER] == TOKEN


def test_balance_without_token_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("ASTRO_CREDITS_TOKEN", raising=False)
    with pytest.raises(InvalidTokenError) as e:
        Client(base_url="https://api.test", transport=FakeAPI()).balance()
    assert e.value.code == "NO_TOKEN"


def test_buy_credits_without_key_or_extra_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("EVM_PRIVATE_KEY", raising=False)
    api = FakeAPI()
    with pytest.raises(InputError):
        client(api).buy_credits("probe")
    assert api.requests == []


def test_merge_events_aligns_time_resolutions():
    from astro_agents import merge_events
    candles = pd.DataFrame({"open_time": pd.date_range("2024-04-07", "2024-04-10", freq="D", tz="UTC")})
    candles["open_time"] = candles["open_time"].astype("datetime64[us, UTC]")
    events = pd.DataFrame({"time": pd.to_datetime([1712600220], unit="s", utc=True).astype("datetime64[s, UTC]"),
                           "type": ["eclipse"], "body": [None], "key": ["eclipse:solar:total:2024-04-08T18:17Z"]})
    out = merge_events(candles, events, on="open_time", tolerance="2D")
    assert list(out["type"].fillna("-")) == ["-", "-", "eclipse", "eclipse"]


def test_examples_compile_and_notebook_is_valid():
    import py_compile
    from pathlib import Path
    ex = Path(__file__).resolve().parents[1] / "examples"
    scripts = sorted(ex.glob("*.py"))
    assert {p.name for p in scripts} >= {"events_ohlc_merge.py", "vectorbt_planetary_lines.py",
                                         "backtrader_planetary_lines.py", "freqtrade_astro_strategy.py"}
    for p in scripts:
        py_compile.compile(str(p), doraise=True)
    nb = json.loads((ex / "quickstart.ipynb").read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and all(c["cell_type"] in ("markdown", "code") for c in nb["cells"])
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            compile("".join(c["source"]), "cell", "exec")
            assert c["outputs"] == []                               # committed without outputs
