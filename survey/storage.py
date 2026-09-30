"""Append-only JSONL storage for raw samples. Raw files are never edited or deleted."""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from .config import ROOT

RAW_DIR = ROOT / "results" / "raw"
PILOT_DIR = ROOT / "results" / "pilot"


def results_dir(pilot: bool) -> Path:
    return PILOT_DIR if pilot else RAW_DIR


def run_path(model_slug: str, run_id: str, pilot: bool) -> Path:
    return results_dir(pilot) / model_slug / f"{run_id}.jsonl"


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def iter_records(base: Path, model_slug: str | None = None):
    pattern = f"{model_slug}/*.jsonl" if model_slug else "*/*.jsonl"
    for p in sorted(base.glob(pattern)):
        with p.open() as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def completed_counts(base: Path) -> tuple[Counter, dict[str, set[int]]]:
    """Successful samples per cell id, and which sample indices are done (for resuming)."""
    counts: Counter = Counter()
    done: dict[str, set[int]] = {}
    for r in iter_records(base):
        if r.get("ok"):
            counts[r["cell_id"]] += 1
            done.setdefault(r["cell_id"], set()).add(r["sample_idx"])
    return counts, done


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "survey"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
