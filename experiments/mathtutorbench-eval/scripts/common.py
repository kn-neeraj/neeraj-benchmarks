"""Shared helpers: config loading, the OpenCode Go client, and usage tracking.

All three models under test AND the judge model draw from one OpenCode Go
subscription and its single set of usage caps ($12/5h, $30/week, $60/month).
The API does not report a real per-request dollar cost (every response comes
back with "cost": "0" regardless of token volume - confirmed live), so the
guardrail here tracks request count and token volume as a proxy and warns
before continuing past a user-specified fraction of a user-specified cap.
Treat this as directional, not authoritative - check the OpenCode dashboard
for actual dollar spend.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

REPO_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(REPO_ROOT / ".env")


def load_config() -> Dict[str, Any]:
    with open(REPO_ROOT / "config" / "models.yaml") as f:
        return yaml.safe_load(f)


class RetryableAPIError(Exception):
    pass


@dataclass
class UsageTracker:
    """Proxy usage tracker: request counts and tokens, since the API does not
    expose real per-request dollar cost."""

    max_requests: Optional[int] = None
    warn_fraction: float = 0.8
    requests_made: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    _warned: bool = field(default=False, repr=False)

    def record(self, usage: Dict[str, Any]) -> None:
        self.requests_made += 1
        self.prompt_tokens += usage.get("prompt_tokens", 0) or 0
        self.completion_tokens += usage.get("completion_tokens", 0) or 0
        if self.max_requests and not self._warned:
            frac = self.requests_made / self.max_requests
            if frac >= self.warn_fraction:
                print(
                    f"[usage] WARNING: {self.requests_made}/{self.max_requests} requests "
                    f"used ({frac:.0%}) against the --max-requests budget you set. "
                    f"Check the OpenCode dashboard for actual dollar spend against your "
                    f"$12/5h, $30/week, $60/month caps.",
                    file=sys.stderr,
                )
                self._warned = True
        if self.max_requests and self.requests_made > self.max_requests:
            raise RuntimeError(
                f"Stopping: {self.requests_made} requests exceeds --max-requests={self.max_requests}. "
                f"Re-run with a higher cap once you've confirmed real spend on the OpenCode dashboard."
            )

    def summary(self) -> Dict[str, Any]:
        return {
            "requests_made": self.requests_made,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
        }


class OpenCodeGoClient:
    def __init__(self, config: Dict[str, Any], usage: Optional[UsageTracker] = None):
        api_key = os.environ.get("OPENCODE_GO_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENCODE_GO_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        self.base_url = config["api"]["base_url"].rstrip("/")
        self.chat_path = config["api"]["chat_endpoint"]
        self.usage = usage or UsageTracker()
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            # A plain float timeout in httpx caps time between successive
            # chunks, not total request time - a slow-trickling stream (e.g. a
            # model reasoning at length) can dodge it for a very long time
            # (observed: 15+ min hang on a judge call before reasoning_effort
            # was set explicitly). Cap total time explicitly instead.
            timeout=httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
        )

    @retry(
        retry=retry_if_exception_type(RetryableAPIError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 512,
        reasoning_effort: Optional[str] = None,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if stop:
            payload["stop"] = stop

        t0 = time.time()
        try:
            resp = self._client.post(self.chat_path, json=payload)
        except httpx.TransportError as e:
            raise RetryableAPIError(str(e)) from e
        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} (non-retryable): {resp.text[:500]}")

        data = resp.json()
        usage = data.get("usage", {}) or {}
        self.usage.record(usage)

        choice = data["choices"][0]
        message = choice.get("message", {}) or {}
        content = message.get("content") or ""
        # Some models (e.g. kimi-k3 with reasoning on) can return an empty
        # content field with the text sitting in a reasoning field instead.
        if not content:
            content = message.get("reasoning") or ""

        return {
            "content": content.strip(),
            "finish_reason": choice.get("finish_reason"),
            "usage": usage,
            "latency_ms": latency_ms,
            "raw_id": data.get("id"),
        }


def truncate_at_stop(text: str, stop: Optional[List[str]]) -> str:
    """Client-side stop-string truncation, in case the server doesn't apply it."""
    if not text or not stop:
        return text
    cut = len(text)
    for s in stop:
        idx = text.find(s)
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut].strip()


def jsonl_read(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def jsonl_append(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")
