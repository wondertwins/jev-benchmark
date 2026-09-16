"""Async wrapper around the TypeSafe SDK with concurrency limits and raw persistence."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeAPIError

RAW_DIR = Path(__file__).resolve().parent.parent / "runs" / "raw"


def _to_jsonable(obj: Any) -> Any:
    """Convert SDK question objects (msgspec structs) to plain JSON for persistence."""
    try:
        import msgspec
        return msgspec.to_builtins(obj)
    except Exception:  # noqa: BLE001
        pass
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj if isinstance(obj, (str, int, float, bool)) or obj is None else repr(obj)


@dataclass
class UsageTally:
    requests: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        lat = sorted(self.latency_s)
        return {
            "requests": self.requests,
            "failures": self.failures,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_p50_s": round(lat[len(lat) // 2], 2) if lat else None,
            "latency_max_s": round(lat[-1], 2) if lat else None,
        }


class JevClient:
    """Rate-limited async client that persists every raw request/response pair."""

    def __init__(self, model: str = "jev-latest", concurrency: int = 4, tag: str = "run"):
        self.model = model
        self.tag = tag
        self._sem = asyncio.Semaphore(concurrency)
        self._client = AsyncTypeSafeClient(
            model=model,
            timeout=60.0,
            retry=RetryPolicy(max_retries=6, backoff_initial=1.0, backoff_max=20.0, timeout=90.0),
        )
        self.usage = UsageTally()
        RAW_DIR.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self) -> "JevClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.__aexit__(*exc)

    async def ask(self, state: Any, questions: dict[str, Any], meta: dict[str, Any] | None = None):
        """Send one System One request. Returns the SDK response, or None on failure."""
        req_json = {"model": self.model, "state": state, "questions": _to_jsonable(questions)}
        key = hashlib.sha256(json.dumps(req_json, sort_keys=True, default=str).encode()).hexdigest()[:16]
        path = RAW_DIR / f"{self.tag}_{key}.json"
        async with self._sem:
            t0 = time.perf_counter()
            self.usage.requests += 1
            try:
                resp = await self._client.system_one(state, questions)
            except TypeSafeAPIError as e:
                self.usage.failures += 1
                path.write_text(json.dumps({"request": req_json, "meta": meta, "error": {
                    "status": getattr(e, "status", None), "request_id": getattr(e, "request_id", None),
                    "message": str(e)}}, indent=1, default=str))
                return None
            except Exception as e:  # noqa: BLE001 - record and continue
                self.usage.failures += 1
                path.write_text(json.dumps({"request": req_json, "meta": meta, "error": {"message": repr(e)}},
                                           indent=1, default=str))
                return None
            dt = time.perf_counter() - t0
        self.usage.latency_s.append(dt)
        self.usage.input_tokens += resp.usage.input_tokens
        self.usage.output_tokens += resp.usage.output_tokens
        raw = None
        try:
            raw = resp.raw_http_response.json()
        except Exception:  # noqa: BLE001
            raw = _to_jsonable(resp)
        path.write_text(json.dumps({"request": req_json, "meta": meta, "latency_s": dt, "response": raw},
                                   indent=1, default=str))
        return resp
