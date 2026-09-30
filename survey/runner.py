"""Resumable async runner.

- Skips samples already present (ok) in the target results directory, so re-running tops cells up to n.
- Per-model concurrency; the client retries 429/5xx with exponential backoff.
- Failed samples are written as ok=false records (never dropped) and retried in later passes.
- Stops when spent-so-far plus the projected cost of the next request would exceed the hard cap.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from collections import Counter
from dataclasses import asdict

from .client import OpenRouter, Response, build_body
from .config import Config
from .prompts import Cell, render
from .storage import PILOT_DIR, RAW_DIR, append, completed_counts, git_commit, iter_records, results_dir, run_path


class BudgetExceeded(RuntimeError):
    pass


def spent_so_far() -> float:
    total = 0.0
    for base in (PILOT_DIR, RAW_DIR):
        for r in iter_records(base):
            total += float(r.get("cost") or 0.0)
    return total


class Budget:
    def __init__(self, cap: float, spent: float):
        self.cap, self.spent, self.reserved = cap, spent, 0.0
        self.lock = asyncio.Lock()

    async def reserve(self, amount: float) -> None:
        async with self.lock:
            if self.spent + self.reserved + amount > self.cap:
                raise BudgetExceeded(f"spent ${self.spent:.2f} + in flight ${self.reserved:.2f} + next "
                                     f"${amount:.4f} would exceed cap ${self.cap:.2f}")
            self.reserved += amount

    async def settle(self, reserved: float, actual: float) -> None:
        async with self.lock:
            self.reserved -= reserved
            self.spent += actual


def make_record(*, run_id: str, cell: Cell, sample_idx: int, body: dict, option_order: list[str],
                resp: Response, commit: str, started: float) -> dict:
    b = resp.body or {}
    usage = b.get("usage") or {}
    return {
        "run_id": run_id,
        "cell_id": cell.id,
        "cell": asdict(cell),
        "sample_idx": sample_idx,
        "ok": resp.ok and bool(resp.text),
        "error": resp.error if not resp.ok else (None if resp.text else "empty_content"),
        "attempts": resp.attempts,
        "request": body,                      # full body; auth is a header and never stored
        "option_order": option_order,
        "response_text": resp.text,
        "reasoning": resp.reasoning,
        "reasoning_details": resp.message.get("reasoning_details"),
        "finish_reason": resp.finish_reason,
        "native_finish_reason": ((b.get("choices") or [{}])[0] or {}).get("native_finish_reason"),
        "served_model": b.get("model"),
        "served_provider": b.get("provider"),
        "generation_id": b.get("id"),
        "usage": usage,
        "cost": usage.get("cost"),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "latency_s": round(time.time() - started, 2),
        "harness_commit": commit,
    }


async def run_cells(cfg: Config, cells: list[Cell], n: int, *, run_id: str, pilot: bool,
                    est_cost_per_sample: dict[str, float], max_passes: int = 3,
                    client: OpenRouter | None = None) -> dict:
    base = results_dir(pilot)
    budget = Budget(float(cfg.budget["hard_cap_usd"]), spent_so_far())
    commit = git_commit()
    own_client = client is None
    client = client or OpenRouter()
    sems = {slug: asyncio.Semaphore(cfg.models[slug].concurrency) for slug in {c.model for c in cells}}
    stop = asyncio.Event()
    stop_reason: list[str] = []

    async def one(cell: Cell, idx: int) -> bool:
        if stop.is_set():
            return False
        model = cfg.models[cell.model]
        r = render(cfg, cell, idx)
        body = build_body(model, r.messages, cell.effort)
        est = est_cost_per_sample.get(cell.model, 0.0)
        async with sems[cell.model]:
            try:
                await budget.reserve(est)
            except BudgetExceeded as e:
                stop.set()
                stop_reason.append(str(e))
                return False
            started = time.time()
            resp = await client.chat(body)
            rec = make_record(run_id=run_id, cell=cell, sample_idx=idx, body=body,
                              option_order=r.option_order, resp=resp, commit=commit, started=started)
            await budget.settle(est, float(rec["cost"] or 0.0))
            append(run_path(cell.model, run_id, pilot), rec)
            return rec["ok"]

    try:
        for _ in range(max_passes):
            _, done = completed_counts(base)
            todo = [(c, i) for c in cells for i in range(n) if i not in done.get(c.id, set())]
            if not todo or stop.is_set():
                break
            await asyncio.gather(*(one(c, i) for c, i in todo))
    finally:
        if own_client:
            await client.aclose()

    counts, _ = completed_counts(base)
    failures: Counter = Counter()
    for rec in iter_records(base):
        if rec.get("run_id") == run_id and not rec.get("ok"):
            failures[rec["cell_id"]] += 1
    short = {c.label(): n - counts.get(c.id, 0) for c in cells if counts.get(c.id, 0) < n}
    return {"spent_total": budget.spent, "stopped": stop_reason[:1], "failed_attempts_per_cell":
            {c.label(): failures[c.id] for c in cells if failures[c.id]}, "cells_short_of_n": short}
