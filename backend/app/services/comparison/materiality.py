"""Deterministic materiality floor (Architecture §10 step 3).

Given two versions of a clause, extract the material tokens (money, numbers with
units, percentages, modal verbs, negations) and derive a *floor* significance.
The AI pass may only raise significance above this floor, never lower it. This
module is pure and fully testable — the safety net for honest comparisons.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.comparison.categories import HIGH_RISK, classify
from app.services.comparison.clauses import aggressive_normalize

CURRENCY = r"(?:AED|USD|EUR|GBP|SAR|QAR|KWD|OMR|BHD|JOD|Dhs)"
_MONEY_PRE = re.compile(CURRENCY + r"\s*([\d][\d,]*(?:\.\d+)?)", re.IGNORECASE)
_MONEY_POST = re.compile(r"([\d][\d,]*(?:\.\d+)?)\s*" + CURRENCY, re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# A quantity is a number followed by the unit it counts. Short periods (hours,
# minutes) are exactly as material as days — a notification window tightened from
# 48 to 24 hours is a real commercial change — so the unit vocabulary is not
# limited to day/month/year, and the number may carry thousands separators or a
# decimal part.
_NUM_UNIT = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(business days?|calendar days?|working days?|days?|"
    r"hours?|minutes?|seconds?|months?|years?|weeks?|quarters?)",
    re.IGNORECASE,
)
_MODALS = re.compile(
    r"\b(shall not|must not|may not|shall|must|may|will|should)\b", re.IGNORECASE
)
_NEGATIONS = re.compile(r"\b(not|never|without|unless)\b", re.IGNORECASE)
_UNLIMITED = re.compile(r"\bunlimited\b", re.IGNORECASE)


def _amount(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass
class Tokens:
    money: dict[str, float] = field(default_factory=dict)  # currency -> value
    percents: list[float] = field(default_factory=list)
    # unit -> every value stated with that unit. A clause may state several
    # periods of the same unit ("cured within 30 days ... on 15 days notice");
    # keeping them as a list means one period cannot silently overwrite another.
    num_units: dict[str, list[float]] = field(default_factory=dict)
    modals: set[str] = field(default_factory=set)
    negations: set[str] = field(default_factory=set)
    unlimited: bool = False


def extract_tokens(text: str) -> Tokens:
    t = Tokens()
    for cur, val in _pairs(text):
        t.money[cur.upper()] = val
    t.percents = sorted(float(p) for p in _PERCENT.findall(text))
    for n, unit in _NUM_UNIT.findall(text):
        t.num_units.setdefault(unit.lower().strip(), []).append(_amount(n))
    for unit in t.num_units:
        t.num_units[unit].sort()
    t.modals = {m.lower() for m in _MODALS.findall(text)}
    t.negations = {n.lower() for n in _NEGATIONS.findall(text)}
    t.unlimited = bool(_UNLIMITED.search(text))
    return t


def _pairs(text: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for m in _MONEY_PRE.finditer(text):
        cur = text[m.start(): m.start() + 3]
        out.append((cur, _amount(m.group(1))))
    for m in _MONEY_POST.finditer(text):
        cur = _trailing_currency(text, m.end())
        if cur:
            out.append((cur, _amount(m.group(1))))
    return out


def _trailing_currency(text: str, end: int) -> str:
    tail = text[end:].lstrip()[:4]
    m = re.match(CURRENCY, tail, re.IGNORECASE)
    return m.group(0) if m else ""


def _units(t: Tokens) -> dict[str, list[float]]:
    """Quantity tokens compared as multisets per unit ("days": [15, 30])."""
    return {u: sorted(v) for u, v in t.num_units.items()}


def _changed_money(a: Tokens, b: Tokens) -> tuple[bool, float]:
    """Return (changed, max_ratio). ratio > 1 means B larger."""
    ratio = 1.0
    changed = False
    for cur in set(a.money) | set(b.money):
        av, bv = a.money.get(cur), b.money.get(cur)
        if av != bv:
            changed = True
            if av and bv:
                ratio = max(ratio, bv / av, av / bv)
            else:
                ratio = max(ratio, 2.0)  # added/removed amount is a big swing
    return changed, ratio


@dataclass
class Materiality:
    significance: str          # HIGH | MEDIUM | LOW | COSMETIC
    changed_tokens: list[str]
    category: str | None


def floor_significance(a_text: str, b_text: str) -> Materiality:
    """Compute the deterministic floor significance for an A->B clause change."""
    category = classify(a_text) or classify(b_text)
    changed: list[str] = []

    ta, tb = extract_tokens(a_text), extract_tokens(b_text)

    money_changed, ratio = _changed_money(ta, tb)
    if money_changed:
        for cur in sorted(set(ta.money) | set(tb.money)):
            av, bv = ta.money.get(cur), tb.money.get(cur)
            if av != bv:
                changed.append(f"{cur} {_fmt(av)} \u2192 {_fmt(bv)}")

    if sorted(ta.percents) != sorted(tb.percents):
        changed.append(
            f"percentage {_fmt_list(ta.percents)} \u2192 {_fmt_list(tb.percents)}"
        )
    if _units(ta) != _units(tb):
        for u in sorted(set(ta.num_units) | set(tb.num_units)):
            av, bv = ta.num_units.get(u, []), tb.num_units.get(u, [])
            if av != bv:
                changed.append(f"{u}: {_fmt_list(av)} \u2192 {_fmt_list(bv)}")
    if ta.modals != tb.modals:
        added = tb.modals - ta.modals
        removed = ta.modals - tb.modals
        changed.append(
            "obligation words changed: "
            + ", ".join(sorted(list(removed) + list(added)))
        )
    if ta.negations != tb.negations:
        changed.append("negation changed")
    if ta.unlimited != tb.unlimited:
        changed.append("liability limit added/removed")

    material_token_change = bool(changed)

    # No material token change.
    if not material_token_change:
        if aggressive_normalize(a_text) == aggressive_normalize(b_text):
            return Materiality("COSMETIC", changed, category)
        return Materiality("LOW", changed, category)

    # Money/percent jump of >= 2x, or a direction change, in a high-risk clause.
    high_risk = category in HIGH_RISK
    direction_flip = ta.modals != tb.modals or ta.negations != tb.negations
    big_amount = ratio >= 2.0 or sorted(ta.percents) != sorted(tb.percents)

    if high_risk and (big_amount or direction_flip):
        return Materiality("HIGH", changed, category)
    return Materiality("MEDIUM", changed, category)


def _fmt(v: float | None) -> str:
    if v is None:
        return "(none)"
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"


def _fmt_list(vals: list[float]) -> str:
    return ", ".join(_fmt(v) for v in vals) if vals else "(none)"
