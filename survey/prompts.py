"""Cells and prompt construction.

A cell is one combination of question x cue x answer format x reasoning effort x model. Samples within a
cell differ only in sampling noise and (for list questions) the randomized option order, which is seeded
from the cell id and sample index so a resumed run renders exactly the same prompt for a given sample.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass

from .config import Config, Cue, Question

FORMATS = ("pick", "credence")


@dataclass(frozen=True)
class Cell:
    question: str
    cue: str
    fmt: str        # pick | credence
    effort: str     # default | none | minimal | low | medium | high | xhigh | max
    model: str      # model slug from models.yaml

    @property
    def id(self) -> str:
        key = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def label(self) -> str:
        return f"{self.model}|{self.question}|{self.cue}|{self.fmt}|{self.effort}"


@dataclass(frozen=True)
class Rendered:
    messages: list[dict]
    option_order: list[str]     # option codes in the order shown; [] for fixed questions


def option_order(q: Question, cell_id: str, sample_idx: int) -> list[str]:
    """Randomize non-anchored options; anchored ones (agnostic, other) stay last in config order."""
    if q.kind != "list":
        return []
    free = [o.code for o in q.options if not o.anchor]
    anchored = [o.code for o in q.options if o.anchor]
    seed = int(hashlib.sha256(f"{cell_id}:{sample_idx}".encode()).hexdigest()[:16], 16)
    random.Random(seed).shuffle(free)
    return free + anchored


def question_text(q: Question, fmt: str, order: list[str], credence_instruction: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt}")
    if q.kind == "fixed":
        if fmt != "pick":
            raise ValueError(f"{q.id}: credence format is only defined for list questions")
        return q.text.strip()
    if fmt == "pick":
        lines = [f"- {q.option(c).label}" for c in order]
        return f"{q.stem} {q.pick_instruction}\n\n" + "\n".join(lines)
    keys = ", ".join(f'"{c}"' for c in order)
    lines = [f"- {c}: {q.option(c).label}" for c in order]
    return f"{q.stem} {credence_instruction.format(keys=keys)}\n\n" + "\n".join(lines)


def render(cfg: Config, cell: Cell, sample_idx: int) -> Rendered:
    q: Question = cfg.questions[cell.question]
    cue: Cue = cfg.cues[cell.cue]
    order = option_order(q, cell.id, sample_idx)
    body = question_text(q, cell.fmt, order, cfg.credence_instruction)
    messages: list[dict] = []
    if cue.placement == "system":
        messages.append({"role": "system", "content": cue.text})
    elif cue.placement == "user_prefix":
        body = f"{cue.text} {body}"
    elif cue.placement == "user_suffix":
        body = f"{body}\n\n{cue.text}"
    elif cue.placement != "none":
        raise ValueError(f"unknown placement {cue.placement}")
    messages.append({"role": "user", "content": body})
    return Rendered(messages=messages, option_order=order)


def expand_design(cfg: Config, design: dict) -> list[Cell]:
    """Expand a design block from designs.yaml into cells.

    design keys: questions (list), cues ("from_question" or list or cue_set name), formats, efforts
    ("model" = every effort in the model's config), models ("enabled" or list of slugs).
    """
    models = ([m.slug for m in cfg.models.values() if m.enabled] if design.get("models", "enabled") == "enabled"
              else list(design["models"]))
    cells: list[Cell] = []
    for qid in design["questions"]:
        q = cfg.questions[qid]
        cues_spec = design.get("cues", "from_question")
        if cues_spec == "from_question":
            cue_ids = cfg.cue_sets[q.cue_set]
        elif isinstance(cues_spec, str):
            cue_ids = cfg.cue_sets[cues_spec]
        else:
            cue_ids = list(cues_spec)
        for cue in cue_ids:
            for fmt in design.get("formats", ["pick"]):
                if fmt == "credence" and q.kind != "list":
                    continue
                for slug in models:
                    m = cfg.models[slug]
                    efforts = design.get("efforts", ["default"])
                    if efforts == "model":
                        efforts = list(m.efforts)
                    for eff in efforts:
                        if eff != "default" and eff not in m.efforts:
                            continue   # model does not support this effort level
                        if eff == "none" and m.reasoning_mandatory:
                            continue
                        cells.append(Cell(question=qid, cue=cue, fmt=fmt, effort=eff, model=slug))
    return cells
