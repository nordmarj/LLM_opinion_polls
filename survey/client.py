"""Thin OpenRouter client.

Kept deliberately small so the exact request body is visible and can be stored verbatim (minus auth).
The API key is read from the environment (.env via python-dotenv) and is never logged or returned.
"""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

from .config import Model

BASE_URL = "https://openrouter.ai/api/v1"
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}


def build_body(model: Model, messages: list[dict], effort: str) -> dict:
    """The full request body. `effort` is "default" (send no reasoning field) or an effort level."""
    body: dict = {"model": model.id, "messages": messages, "max_tokens": model.max_tokens}
    if effort != "default":
        body["reasoning"] = {"effort": effort}
    provider: dict = {"require_parameters": True, "allow_fallbacks": False}
    if model.provider_order:
        provider["order"] = list(model.provider_order)
    body["provider"] = provider
    return body


@dataclass
class Response:
    ok: bool
    status: int | None
    body: dict = field(default_factory=dict)   # parsed JSON response (no auth material in it)
    error: str | None = None
    attempts: int = 1

    @property
    def message(self) -> dict:
        try:
            return self.body["choices"][0]["message"] or {}
        except (KeyError, IndexError, TypeError):
            return {}

    @property
    def text(self) -> str:
        return self.message.get("content") or ""

    @property
    def reasoning(self) -> str | None:
        return self.message.get("reasoning")

    @property
    def finish_reason(self) -> str | None:
        try:
            return self.body["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError):
            return None


class OpenRouter:
    def __init__(self, api_key: str | None = None, *, timeout: float = 600.0, max_attempts: int = 6,
                 transport: httpx.AsyncBaseTransport | None = None):
        load_dotenv()
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        self.max_attempts = max_attempts

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, body: dict) -> Response:
        """POST /chat/completions with exponential backoff on 429/5xx and transport errors."""
        last_err, last_status = None, None
        for attempt in range(1, self.max_attempts + 1):
            try:
                r = await self._client.post("/chat/completions", json=body)
            except httpx.TransportError as e:
                last_err, last_status = f"{type(e).__name__}: {e}", None
            else:
                last_status = r.status_code
                try:
                    data = r.json()
                except ValueError:
                    data = {}
                # OpenRouter can return 200 with an error object (e.g. upstream failure mid-request).
                err = data.get("error") if isinstance(data, dict) else None
                if r.status_code == 200 and not err:
                    return Response(ok=True, status=200, body=data, attempts=attempt)
                code = (err or {}).get("code", r.status_code) if isinstance(err, dict) else r.status_code
                last_err = f"HTTP {r.status_code}: {str(err or r.text)[:500]}"
                retryable = r.status_code in RETRY_STATUS or (isinstance(code, int) and code in RETRY_STATUS)
                if not retryable:
                    return Response(ok=False, status=r.status_code, body=data, error=last_err, attempts=attempt)
            if attempt < self.max_attempts:
                await asyncio.sleep(min(60.0, 2 ** attempt) * (0.5 + random.random()))
        return Response(ok=False, status=last_status, error=last_err, attempts=self.max_attempts)

    async def generation(self, gen_id: str) -> dict:
        """GET /generation?id=... : served provider name and exact cost for a completed request."""
        r = await self._client.get("/generation", params={"id": gen_id})
        r.raise_for_status()
        return r.json().get("data", {})


async def fetch_public(path: str, params: dict | None = None) -> dict:
    """Unauthenticated GET for public catalog endpoints (/models, /models/{id}/endpoints)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r.json()
