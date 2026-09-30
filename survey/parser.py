"""Deterministic answer coding: extract the tagged answer or JSON credences and map it to an option code.

Anything this cannot resolve unambiguously is left as status "unresolved" for the LLM judge.
Hedging is not coded here (the judge codes it); the parser only records what is inside the tags.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .config import Question

OTHER_PREFIX = re.compile(r"^\s*other\b\s*[:\-–—,(]?\s*", re.I)


@dataclass
class Parsed:
    status: str                         # ok | unresolved | missing
    code: str | None = None             # option code for pick format
    raw: str | None = None              # text inside the answer tag
    other_text: str | None = None       # the named alternative when code == "other"
    credences: dict[str, float] | None = None
    notes: list[str] = field(default_factory=list)


def extract_tag(text: str, tag: str) -> str | None:
    """Content of the last complete <tag>...</tag> (models sometimes echo the instruction first)."""
    matches = re.findall(rf"<{tag}>(.*?)</{tag}>", text or "", flags=re.S | re.I)
    matches = [m.strip() for m in matches if m.strip() and m.strip() not in ("...", "…")]
    return matches[-1] if matches else None


def _pattern(syn: str) -> re.Pattern:
    # word boundaries that also work around hyphens and slashes
    return re.compile(rf"(?<![\w-]){re.escape(syn)}(?![\w-])", re.I)


def _normalize(s: str) -> str:
    s = s.replace("‑", "-").replace("‐", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"[*_`\"“”]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def match_options(text: str, q: Question, exclude: set[str] = frozenset()) -> list[str]:
    """Option codes whose synonyms occur in `text`, ordered by first occurrence."""
    hits: dict[str, int] = {}
    for o in q.options:
        if o.code in exclude:
            continue
        for syn in o.synonyms:
            m = _pattern(syn).search(text)
            if m and (o.code not in hits or m.start() < hits[o.code]):
                hits[o.code] = m.start()
    return sorted(hits, key=hits.get)


def code_pick(answer: str, q: Question) -> Parsed:
    a = _normalize(answer)
    codes = set(q.codes)
    # "Other: consistent histories" -> the listed option if one is named, else other.
    if "other" in codes and OTHER_PREFIX.match(a):
        rest = OTHER_PREFIX.sub("", a, count=1).strip(" ()")
        named = match_options(rest, q, exclude={"other"}) if rest else []
        if len(named) == 1:
            return Parsed("ok", code=named[0], raw=answer, notes=["other_named_listed_option"])
        if not named:
            return Parsed("ok", code="other", raw=answer, other_text=rest or None)
        return Parsed("unresolved", raw=answer, notes=[f"other_with_multiple:{','.join(named)}"])
    hits = match_options(a, q, exclude={"other"})
    if len(hits) == 1:
        return Parsed("ok", code=hits[0], raw=answer)
    if not hits:
        return Parsed("unresolved", raw=answer, notes=["no_option_matched"])
    return Parsed("unresolved", raw=answer, notes=[f"multiple:{','.join(hits)}"])


def code_credences(text: str, q: Question, tol: float = 2.0) -> Parsed:
    raw = extract_tag(text, "credences")
    if raw is None:
        return Parsed("missing", notes=["no_credences_tag"])
    m = re.search(r"\{.*\}", raw, flags=re.S)
    try:
        obj = json.loads(m.group(0) if m else raw)
    except (json.JSONDecodeError, AttributeError):
        return Parsed("unresolved", raw=raw, notes=["bad_json"])
    if not isinstance(obj, dict):
        return Parsed("unresolved", raw=raw, notes=["not_object"])
    creds: dict[str, float] = {}
    for k, v in obj.items():
        key = str(k).strip()
        code = key if key in q.codes else None
        if code is None:
            found = match_options(_normalize(key), q)
            code = found[0] if len(found) == 1 else None
        if code is None:
            return Parsed("unresolved", raw=raw, notes=[f"unknown_key:{key}"])
        try:
            creds[code] = creds.get(code, 0.0) + float(str(v).rstrip("%"))
        except ValueError:
            return Parsed("unresolved", raw=raw, notes=[f"bad_value:{key}"])
    total = sum(creds.values())
    notes = []
    if abs(total - 100) > tol:
        if abs(total - 1) <= tol / 100:   # answered as probabilities
            creds = {k: v * 100 for k, v in creds.items()}
            notes.append("rescaled_from_unit")
        else:
            notes.append(f"sum={total:g}")
            return Parsed("unresolved", raw=raw, credences=creds, notes=notes)
    for c in q.codes:
        creds.setdefault(c, 0.0)
    top = max(creds, key=creds.get)
    return Parsed("ok", code=top, raw=raw, credences=creds, notes=notes)


def parse_response(text: str, q: Question, fmt: str) -> Parsed:
    if fmt == "credence":
        return code_credences(text, q)
    ans = extract_tag(text, q.answer_tag)
    if ans is None:
        return Parsed("missing", notes=[f"no_{q.answer_tag}_tag"])
    return code_pick(ans, q)
