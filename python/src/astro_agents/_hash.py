"""The service's reproducibility rule, offline: result_sha256 = SHA-256 of the result serialized
as JSON with sorted keys, no whitespace, UTF-8, floats rounded to 6 decimals."""
from __future__ import annotations

import hashlib
import json
import math

DECIMALS = 6


def canonical(obj):
    if isinstance(obj, dict):
        return {str(k): canonical(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [canonical(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    try:
        f = float(obj)
    except (TypeError, ValueError):
        return str(obj)
    if not math.isfinite(f):
        return None
    r = round(f, DECIMALS)
    return 0.0 if r == 0 else r


def result_sha256(result) -> str:
    """The result_sha256 of a result object, as the service computes it."""
    data = json.dumps(canonical(result), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
