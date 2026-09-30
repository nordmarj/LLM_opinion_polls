"""LLM judge for answers the deterministic parser cannot resolve, plus hedge coding.

Rules (see CLAUDE.md): judge model from a different family than the coded model where possible; fixed
rubric in rubric.md; labels cached by (rubric version, judge model, text hash) so re-coding is free and
reproducible.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..config import ROOT, Question

RUBRIC_PATH = Path(__file__).with_name("rubric.md")
CACHE_PATH = ROOT / "results" / "derived" / "judge_cache.jsonl"
RUBRIC_VERSION = "1"


def pick_judge(coded_family: str, judges: dict[str, str]) -> str:
    """judges: family -> judge model id (from budget.yaml `judges`). Use the first of another family."""
    for fam, mid in judges.items():
        if fam != coded_family:
            return mid
    return next(iter(judges.values()))


def answer_rubric() -> str:
    text = RUBRIC_PATH.read_text()
    return text.split("\n---\n")[0]


def reasoning_rubric() -> str:
    return RUBRIC_PATH.read_text().split("\n---\n")[1]


def answer_prompt(q: Question, question_text: str, response_text: str) -> list[dict]:
    opts = "\n".join(f"- {o.code}: {o.label}" for o in q.options)
    user = (f"<question>\n{question_text}\n</question>\n<allowed_codes>\n{opts}\n</allowed_codes>\n"
            f"<answer>\n{response_text}\n</answer>\nReturn the JSON object.")
    return [{"role": "system", "content": answer_rubric()}, {"role": "user", "content": user}]


def cache_key(judge_model: str, kind: str, text: str) -> str:
    return hashlib.sha256(f"{RUBRIC_VERSION}|{judge_model}|{kind}|{text}".encode()).hexdigest()[:24]


def load_cache(path: Path = CACHE_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.open():
        if line.strip():
            r = json.loads(line)
            out[r["key"]] = r["label"]
    return out


def parse_judge_output(text: str, q: Question) -> dict | None:
    m = re.search(r"\{.*\}", text or "", flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if obj.get("option") not in q.codes:
        return None
    if obj.get("lean") not in (None, *q.codes):
        obj["lean"] = None
    obj["hedged"] = bool(obj.get("hedged"))
    return obj
