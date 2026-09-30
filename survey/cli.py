"""Command line: survey models | plan | run | code.

    uv run survey models refresh           # refresh models + endpoints cache (no API key needed)
    uv run survey models show              # configured models, pinned provider, prices
    uv run survey plan --design pilot_core # cells, samples, tokens, cost per model and total
    uv run survey run --design pilot_core --pilot --confirm-cost 12.5
    uv run survey code --pilot             # deterministic parse -> results/derived/coded_pilot.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys

from . import catalog
from .analysis import code_records, summarize, write_coded
from .config import load_config
from .plan import format_plan, plan
from .prompts import expand_design
from .storage import completed_counts, results_dir


def _cells(cfg, args):
    if args.design not in cfg.designs:
        sys.exit(f"unknown design {args.design!r}; have {sorted(cfg.designs)}")
    design = cfg.designs[args.design]
    cells = expand_design(cfg, design)
    if args.models:
        wanted = set(args.models.split(","))
        cells = [c for c in cells if c.model in wanted]
    n = args.n or design.get("n", 10)
    return cells, n


def cmd_models(args):
    cfg = load_config()
    if args.action == "refresh":
        p = catalog.refresh_models()
        print(f"models cache -> {p}")
        ids = sorted({m.id for m in cfg.models.values()})
        p = catalog.refresh_endpoints(ids)
        print(f"endpoints cache ({len(ids)} models) -> {p}")
        return
    cat, eps = catalog.load_models(), catalog.load_endpoints()
    print(f"{'slug':26s} {'id':38s} {'provider':18s} {'$in/M':>7s} {'$out/M':>7s} reasoning")
    for m in cfg.models.values():
        if m.id not in cat:
            print(f"{m.slug:26s} {m.id:38s} NOT IN CATALOG")
            continue
        pin, pout, src = catalog.price_per_token(m, cat, eps)
        r = cat[m.id].get("reasoning") or {}
        flag = "" if m.enabled else "  (disabled)"
        print(f"{m.slug:26s} {m.id:38s} {src:18s} {pin*1e6:7.2f} {pout*1e6:7.2f} "
              f"mandatory={r.get('mandatory')} efforts={r.get('supported_efforts')}{flag}")


def cmd_plan(args):
    cfg = load_config()
    cells, n = _cells(cfg, args)
    counts, _ = completed_counts(results_dir(args.pilot))
    rows = plan(cfg, cells, n, already=dict(counts))
    print(f"design={args.design} n={n} target={'pilot' if args.pilot else 'main'}")
    print(format_plan(rows))
    cap = cfg.budget["hard_cap_usd"]
    print(f"hard cap ${cap}; ask-before threshold ${cfg.budget['ask_above_usd']}")


def cmd_run(args):
    cfg = load_config()
    cells, n = _cells(cfg, args)
    counts, _ = completed_counts(results_dir(args.pilot))
    rows = plan(cfg, cells, n, already=dict(counts))
    print(format_plan(rows))
    total = sum(r.cost for r in rows)
    # Guardrails from CLAUDE.md: ask before >$10 and before the first run on any new model.
    if total > cfg.budget["ask_above_usd"] and (args.confirm_cost is None or args.confirm_cost < total):
        sys.exit(f"estimated ${total:.2f} > ${cfg.budget['ask_above_usd']}: get approval, then pass "
                 f"--confirm-cost {total:.2f} (or higher)")
    approved = set(cfg.budget.get("approved_models") or [])
    new = sorted({c.model for c in cells} - approved)
    if new and not args.approve_new_models:
        sys.exit(f"first run on models {new}: get approval, add them to approved_models in budget.yaml "
                 f"or pass --approve-new-models")
    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_{args.design}"
    est = {r.slug: (r.cost / r.samples if r.samples else 0.0) for r in rows}
    from .runner import run_cells
    report = asyncio.run(run_cells(cfg, cells, n, run_id=run_id, pilot=args.pilot, est_cost_per_sample=est))
    print(json.dumps({"run_id": run_id, **report}, indent=1))


def cmd_code(args):
    cfg = load_config()
    rows = code_records(cfg, results_dir(args.pilot))
    path = write_coded(rows, "pilot" if args.pilot else "main")
    print(f"{len(rows)} rows -> {path}")
    print(summarize(rows))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="survey")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("models")
    m.add_argument("action", choices=["refresh", "show"])
    m.set_defaults(fn=cmd_models)
    for name, fn in (("plan", cmd_plan), ("run", cmd_run)):
        p = sub.add_parser(name)
        p.add_argument("--design", required=True)
        p.add_argument("--n", type=int)
        p.add_argument("--models", help="comma-separated model slugs (subset of the design)")
        p.add_argument("--pilot", action="store_true", help="read/write results/pilot/")
        if name == "run":
            p.add_argument("--confirm-cost", type=float)
            p.add_argument("--approve-new-models", action="store_true")
            p.add_argument("--run-id")
        p.set_defaults(fn=fn)
    c = sub.add_parser("code")
    c.add_argument("--pilot", action="store_true")
    c.set_defaults(fn=cmd_code)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
