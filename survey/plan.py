"""Cost and size planning. `survey plan` must be run (and read) before every run."""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .catalog import load_endpoints, load_models, price_per_token
from .config import Config
from .prompts import Cell, render
from .storage import PILOT_DIR, RAW_DIR, iter_records


@dataclass
class ModelPlan:
    slug: str
    cells: int
    samples: int
    in_tokens: float
    out_tokens: float
    cost: float
    out_source: str       # where the output-token estimate came from
    price_source: str


def observed_output_tokens(slug: str, bases: tuple[Path, ...] = (PILOT_DIR, RAW_DIR)) -> dict[str, float]:
    """Mean completion tokens (incl. reasoning) per effort from earlier runs of this model."""
    by_eff: dict[str, list[int]] = defaultdict(list)
    for base in bases:
        for r in iter_records(base, slug):
            u = r.get("usage") or {}
            if r.get("ok") and u.get("completion_tokens"):
                by_eff[r["cell"]["effort"]].append(u["completion_tokens"])
    return {e: statistics.mean(v) for e, v in by_eff.items() if len(v) >= 5}


def prior_output_tokens(cfg: Config, slug: str, effort: str) -> float:
    priors = cfg.budget["output_token_priors"]
    per_model = priors.get("models", {}).get(slug, {})
    if effort in per_model:
        return per_model[effort]
    m = cfg.models[slug]
    cls = "reasoning" if (m.reasoning_default_on or effort not in ("default", "none")) else "default"
    return priors["classes"][cls] if effort != "none" else priors["classes"]["none"]


def plan(cfg: Config, cells: list[Cell], n: int, *, already: dict[str, int] | None = None) -> list[ModelPlan]:
    catalog, endpoints = load_models(), load_endpoints()
    already = already or {}
    by_model: dict[str, list[Cell]] = defaultdict(list)
    for c in cells:
        by_model[c.model].append(c)
    out = []
    for slug, cs in by_model.items():
        m = cfg.models[slug]
        pin, pout, psrc = price_per_token(m, catalog, endpoints)
        observed = observed_output_tokens(slug)
        samples = in_tok = out_tok = 0.0
        sources = set()
        for c in cs:
            todo = max(0, n - already.get(c.id, 0))
            if not todo:
                continue
            chars = sum(len(msg["content"]) for msg in render(cfg, c, 0).messages)
            in_each = chars / 3.5 + 15          # rough tokenizer ratio + chat template overhead
            if c.effort in observed:
                out_each, src = observed[c.effort], "observed"
            else:
                out_each, src = prior_output_tokens(cfg, slug, c.effort), "prior"
            sources.add(src)
            samples += todo
            in_tok += todo * in_each
            out_tok += todo * out_each
        cost = in_tok * pin + out_tok * pout
        out.append(ModelPlan(slug, len(cs), int(samples), in_tok, out_tok, cost,
                             "+".join(sorted(sources)) or "-", psrc))
    return out


def format_plan(rows: list[ModelPlan]) -> str:
    lines = [f"{'model':28s} {'cells':>5s} {'samples':>8s} {'in_tok':>10s} {'out_tok':>10s} {'est_$':>9s}  out_est / price",
             "-" * 100]
    for r in sorted(rows, key=lambda r: -r.cost):
        lines.append(f"{r.slug:28s} {r.cells:5d} {r.samples:8d} {r.in_tokens:10.0f} {r.out_tokens:10.0f} "
                     f"{r.cost:9.2f}  {r.out_source} / {r.price_source}")
    tot = sum(r.cost for r in rows)
    lines.append("-" * 100)
    lines.append(f"{'TOTAL':28s} {sum(r.cells for r in rows):5d} {sum(r.samples for r in rows):8d} "
                 f"{sum(r.in_tokens for r in rows):10.0f} {sum(r.out_tokens for r in rows):10.0f} {tot:9.2f}")
    return "\n".join(lines)
