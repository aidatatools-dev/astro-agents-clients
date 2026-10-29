"""Astro Agents: verifiable planetary timing data for market analysis and backtesting, plus Western and
Vedic astrology, from the NASA/JPL DE440 ephemeris. Python client for https://astro-agent.dev."""
__version__ = "0.1.0"

from .client import DEFAULT_BASE_URL, Client, Result, merge_events, verify_dataframe, verify_local  # noqa: E402
from .errors import (AstroAgentsError, InputError, InvalidTokenError, PaymentRequiredError,  # noqa: E402
                     RateLimitError, ServerError, TransportError, VerificationError)
from ._hash import result_sha256  # noqa: E402

__all__ = ["Client", "Result", "merge_events", "verify_local", "verify_dataframe", "result_sha256", "DEFAULT_BASE_URL",
           "AstroAgentsError", "InputError", "InvalidTokenError", "PaymentRequiredError", "RateLimitError",
           "ServerError", "TransportError", "VerificationError", "__version__"]
