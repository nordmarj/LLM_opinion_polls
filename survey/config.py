"""Load the YAML configuration in survey/config/ into plain dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(__file__).resolve().parent / "config"
CACHE_DIR = Path(__file__).resolve().parent / "cache"


@dataclass(frozen=True)
class Option:
    code: str
    label: str
    synonyms: tuple[str, ...]
    anchor: bool = False


@dataclass(frozen=True)
class Question:
    id: str
    kind: str                     # "list" | "fixed"
    family: str                   # qm | dt | ethics | mind | stats
    topic: str
    answer_tag: str
    cue_set: str
    options: tuple[Option, ...]
    stem: str = ""                # list questions
    pick_instruction: str = ""    # list questions
    text: str = ""                # fixed questions

    def option(self, code: str) -> Option:
        for o in self.options:
            if o.code == code:
                return o
        raise KeyError(code)

    @property
    def codes(self) -> list[str]:
        return [o.code for o in self.options]


@dataclass(frozen=True)
class Cue:
    id: str
    placement: str                # none | user_prefix | user_suffix | system
    group: str
    text: str
    modal_view: dict = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True)
class Model:
    id: str                       # OpenRouter model id, copied from the models endpoint
    slug: str                     # filesystem-safe short name
    family: str                   # vendor family for grouping, e.g. anthropic, openai, deepseek
    provider_order: tuple[str, ...] = ()   # provider slugs to pin; empty = let OpenRouter choose
    efforts: tuple[str, ...] = ("default",)
    reasoning_mandatory: bool = False
    reasoning_default_on: bool = False   # for cost priors only
    max_tokens: int = 16000
    concurrency: int = 4
    open_weights: bool = False
    enabled: bool = True
    notes: str = ""


@dataclass
class Config:
    questions: dict[str, Question]
    cues: dict[str, Cue]
    cue_sets: dict[str, list[str]]
    credence_instruction: str
    models: dict[str, Model]
    budget: dict
    designs: dict


def _load(name: str, config_dir: Path) -> dict:
    with open(config_dir / name) as f:
        return yaml.safe_load(f) or {}


def _options(raw: dict) -> tuple[Option, ...]:
    out = []
    for code, o in raw.items():
        code = str(code)
        syn = [str(s).lower() for s in (o.get("synonyms") or [])]
        label = str(o["label"])
        if label.lower() not in syn:
            syn.append(label.lower())
        out.append(Option(code=code, label=label, synonyms=tuple(syn), anchor=bool(o.get("anchor", False))))
    return tuple(out)


def load_config(config_dir: Path = CONFIG_DIR) -> Config:
    qraw = _load("questions.yaml", config_dir)
    questions = {}
    for qid, q in qraw["questions"].items():
        questions[qid] = Question(
            id=qid, kind=q["kind"], family=q["family"], topic=q["topic"], answer_tag=q["answer_tag"],
            cue_set=q["cue_set"], options=_options(q["options"]), stem=q.get("stem", ""),
            pick_instruction=q.get("pick_instruction", ""), text=q.get("text", ""),
        )
    craw = _load("cues.yaml", config_dir)
    cues = {cid: Cue(id=cid, placement=c["placement"], group=c["group"], text=c.get("text", ""),
                     modal_view=c.get("modal_view") or {})
            for cid, c in craw["cues"].items()}
    cue_sets = craw.get("cue_sets", {})
    for name, members in cue_sets.items():
        missing = [m for m in members if m not in cues]
        if missing:
            raise ValueError(f"cue_set {name} references unknown cues {missing}")

    mraw = _load("models.yaml", config_dir)
    models = {}
    for m in mraw.get("models", []):
        models[m["slug"]] = Model(
            id=m["id"], slug=m["slug"], family=m["family"],
            provider_order=tuple(m.get("provider_order") or ()),
            efforts=tuple(m.get("efforts") or ("default",)),
            reasoning_mandatory=bool(m.get("reasoning_mandatory", False)),
            reasoning_default_on=bool(m.get("reasoning_default_on", False)),
            max_tokens=int(m.get("max_tokens", 16000)), concurrency=int(m.get("concurrency", 4)),
            open_weights=bool(m.get("open_weights", False)), enabled=bool(m.get("enabled", True)),
            notes=m.get("notes", ""),
        )
    return Config(
        questions=questions, cues=cues, cue_sets=cue_sets,
        credence_instruction=qraw["credence_instruction"], models=models,
        budget=_load("budget.yaml", config_dir), designs=_load("designs.yaml", config_dir).get("designs", {}),
    )
