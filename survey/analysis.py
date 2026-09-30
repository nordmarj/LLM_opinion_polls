"""Coding raw records into a derived table, and per-cell summaries with Wilson intervals.

Heavier analysis (regressions, figures) needs the `analysis` extra and comes after the pilot.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .config import ROOT, Config
from .parser import parse_response
from .storage import iter_records

DERIVED = ROOT / "results" / "derived"


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def code_records(cfg: Config, base: Path) -> list[dict]:
    rows = []
    for r in iter_records(base):
        if not r.get("ok"):
            continue
        cell = r["cell"]
        q = cfg.questions[cell["question"]]
        p = parse_response(r["response_text"], q, cell["fmt"])
        rows.append({
            "cell_id": r["cell_id"], **cell, "sample_idx": r["sample_idx"], "run_id": r["run_id"],
            "parse_status": p.status, "code": p.code, "raw_answer": p.raw, "other_text": p.other_text,
            "credences": p.credences, "parse_notes": p.notes, "option_order": r.get("option_order"),
            "served_provider": r.get("served_provider"), "has_reasoning": bool(r.get("reasoning")),
            "finish_reason": r.get("finish_reason"),
        })
    return rows


def write_coded(rows: list[dict], name: str) -> Path:
    DERIVED.mkdir(parents=True, exist_ok=True)
    path = DERIVED / f"coded_{name}.jsonl"
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def summarize(rows: list[dict]) -> str:
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        cells[(r["model"], r["question"], r["cue"], r["fmt"], r["effort"])].append(r)
    out = []
    for key in sorted(cells):
        rs = cells[key]
        n = len(rs)
        codes = Counter(r["code"] if r["parse_status"] == "ok" else f"<{r['parse_status']}>" for r in rs)
        parts = []
        for code, k in codes.most_common():
            lo, hi = wilson(k, n)
            parts.append(f"{code} {k}/{n} [{lo:.2f},{hi:.2f}]")
        out.append(" | ".join(key) + "  ->  " + "; ".join(parts))
    return "\n".join(out)
