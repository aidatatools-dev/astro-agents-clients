"""Exceptions raised by the client. Every one carries the HTTP status, the API's error code and
the JSON body, so a caller can branch on `code` without parsing messages."""
from __future__ import annotations

from typing import Any


class AstroAgentsError(Exception):
    """Base class: any error answered by the API, or raised before reaching it."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None,
                 body: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.body = body or {}

    def __str__(self) -> str:
        where = f"HTTP {self.status}" if self.status else "client"
        return f"{self.message} ({where}{', ' + self.code if self.code else ''})"


class InputError(AstroAgentsError):
    """400: the request is invalid (`code`, `field`). Never charged."""

    @property
    def field(self) -> str | None:
        return self.body.get("field")


class InvalidTokenError(AstroAgentsError):
    """401: the credits token is unknown, malformed or revoked. Nothing was charged."""


class PaymentRequiredError(AstroAgentsError):
    """402: this call needs a payment.

    Either there is no token and the free call is used (or the route is always paid), or the
    credits balance is too low (`code == "CREDITS_INSUFFICIENT"`). `price_usd`, `balance_usd`
    and `topup_url` say what to do; `packs` lists the credit packs."""

    @property
    def price_usd(self) -> str | None:
        return self.body.get("price_usd")

    @property
    def balance_usd(self) -> str | None:
        return self.body.get("balance_usd")

    @property
    def topup_url(self) -> str | None:
        return self.body.get("topup")

    @property
    def packs(self) -> list:
        return self.body.get("packs") or []


class RateLimitError(AstroAgentsError):
    """429: too many requests; `retry_after` seconds (raised once retries are exhausted)."""

    def __init__(self, *args, retry_after: float | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class ServerError(AstroAgentsError):
    """5xx, including 503 CREDITS_UNAVAILABLE (nothing charged), after retries."""


class TransportError(AstroAgentsError):
    """The request did not get an answer (network, timeout)."""


class VerificationError(AstroAgentsError):
    """A result does not match its SHA-256."""
