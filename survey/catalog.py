"""OpenRouter model catalog: fetch, cache and look up models, endpoints (providers) and pricing.

Never write model ids from memory: refresh the cache with `survey models refresh` and pick from it.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

from .client import fetch_public
from .config import CACHE_DIR, Model


def today() -> str:
    return dt.date.today().isoformat()


def latest_cache(prefix: str, cache_dir: Path = CACHE_DIR) -> Path | None:
    files = sorted(cache_dir.glob(f"{prefix}_*.json"))
    return files[-1] if files else None


def refresh_models(cache_dir: Path = CACHE_DIR) -> Path:
    data = asyncio.run(fetch_public("/models"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"models_{today()}.json"
    path.write_text(json.dumps(data, indent=1))
    return path


def load_models(cache_dir: Path = CACHE_DIR) -> dict[str, dict]:
    path = latest_cache("models", cache_dir)
    if path is None:
        raise FileNotFoundError("no models cache; run `survey models refresh`")
    return {m["id"]: m for m in json.loads(path.read_text())["data"]}


def refresh_endpoints(model_ids: list[str], cache_dir: Path = CACHE_DIR) -> Path:
    async def go():
        out = {}
        for mid in model_ids:
            try:
                out[mid] = (await fetch_public(f"/models/{mid}/endpoints"))["data"]
            except Exception as e:   # keep going; record the failure
                out[mid] = {"error": f"{type(e).__name__}: {e}"}
        return out

    data = asyncio.run(go())
    path = cache_dir / f"endpoints_{today()}.json"
    path.write_text(json.dumps(data, indent=1))
    return path


def load_endpoints(cache_dir: Path = CACHE_DIR) -> dict[str, dict]:
    path = latest_cache("endpoints", cache_dir)
    return json.loads(path.read_text()) if path else {}


def pinned_endpoint(model: Model, endpoints: dict[str, dict]) -> dict | None:
    """Endpoint entry for the first provider in the model's provider_order (exact tag match first)."""
    eps = (endpoints.get(model.id) or {}).get("endpoints") or []
    if not eps:
        return None
    if not model.provider_order:
        return None
    want = model.provider_order[0]
    for e in eps:
        if e.get("tag") == want:
            return e
    for e in eps:
        if (e.get("tag") or "").split("/")[0] == want.split("/")[0]:
            return e
    return None


def price_per_token(model: Model, catalog: dict[str, dict], endpoints: dict[str, dict]) -> tuple[float, float, str]:
    """(input $/token, output $/token, source). Pinned provider's price if known, else catalog price.

    The catalog price is the cheapest provider's, which for open-weight models can be far below the
    first-party provider's, so the pinned endpoint price is preferred.
    """
    ep = pinned_endpoint(model, endpoints)
    if ep:
        return float(ep["pricing"]["prompt"]), float(ep["pricing"]["completion"]), f"endpoint:{ep.get('tag')}"
    m = catalog.get(model.id)
    if m is None:
        raise KeyError(f"{model.id} not in the models cache")
    return float(m["pricing"]["prompt"]), float(m["pricing"]["completion"]), "catalog"
