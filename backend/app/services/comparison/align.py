"""Clause alignment (Architecture §10 step 2).

Pairs clauses between two documents and types each difference. Moved clauses
are detected from identical content appearing out of order, so they are reported
as MOVED rather than an Added + Removed pair (the compare-cli lesson).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.comparison.clauses import Clause
from app.services.comparison.materiality import floor_significance
from app.services.comparison.similarity import dice

SIM_NUMBERED = 0.5
SIM_BEST = 0.6


@dataclass
class Change:
    type: str            # ADDED | REMOVED | MODIFIED | MOVED | COSMETIC
    significance: str    # HIGH | MEDIUM | LOW | COSMETIC
    category: str | None
    title: str
    summary: str
    a_text: str | None
    b_text: str | None
    a_start: int | None
    a_end: int | None
    b_start: int | None
    b_end: int | None


def _lis(indices: list[int]) -> set[int]:
    """Positions (in ``indices``) belonging to a longest increasing subsequence."""
    if not indices:
        return set()
    n = len(indices)
    dp = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if indices[j] < indices[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                prev[i] = j
    best = max(range(n), key=lambda i: dp[i])
    in_lis: set[int] = set()
    cur = best
    while cur != -1:
        in_lis.add(cur)
        cur = prev[cur]
    return in_lis


def _title(clause: Clause | None) -> str:
    if clause is None:
        return ""
    if clause.number:
        return clause.number
    words = clause.text.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")


def align(a_clauses: list[Clause], b_clauses: list[Clause]) -> list[Change]:
    changes: list[Change] = []

    # 1. Exact-content matches (aggressive-normalised key equality).
    b_by_key: dict[str, list[int]] = {}
    for i, c in enumerate(b_clauses):
        b_by_key.setdefault(c.key, []).append(i)

    key_pairs: list[tuple[int, int]] = []
    used_a: set[int] = set()
    used_b: set[int] = set()
    for i, ca in enumerate(a_clauses):
        candidates = [j for j in b_by_key.get(ca.key, []) if j not in used_b]
        if candidates:
            j = candidates[0]
            key_pairs.append((i, j))
            used_a.add(i)
            used_b.add(j)

    # 2. Among identical-content pairs, detect MOVED via LIS on B-order.
    b_positions = [j for _, j in key_pairs]
    lis_positions = _lis(b_positions)
    for k, (i, j) in enumerate(key_pairs):
        ca, cb = a_clauses[i], b_clauses[j]
        if k in lis_positions:
            continue  # in-order and identical: unchanged, not reported
        changes.append(
            Change(
                type="MOVED",
                significance="LOW",
                category=floor_significance(ca.text, ca.text).category,
                title=_title(ca),
                summary=f"Clause moved (was {_title(ca)}, now {_title(cb)}).",
                a_text=ca.text, b_text=cb.text,
                a_start=ca.start, a_end=ca.end, b_start=cb.start, b_end=cb.end,
            )
        )

    # 3. Remaining A vs B: match by number/heading, then best similarity.
    rem_a = [i for i in range(len(a_clauses)) if i not in used_a]
    rem_b = [j for j in range(len(b_clauses)) if j not in used_b]

    # 3a. Same leading number with sufficient similarity -> MODIFIED.
    for i in list(rem_a):
        ca = a_clauses[i]
        best_j, best_score = None, 0.0
        for j in rem_b:
            cb = b_clauses[j]
            same_num = ca.number is not None and ca.number == cb.number
            s = dice(ca.key, cb.key)
            threshold = SIM_NUMBERED if same_num else SIM_BEST
            if s >= threshold and s > best_score:
                best_j, best_score = j, s
        if best_j is not None:
            cb = b_clauses[best_j]
            changes.append(_modified(ca, cb))
            rem_a.remove(i)
            rem_b.remove(best_j)

    # 3b. Leftovers: unmatched A -> REMOVED, unmatched B -> ADDED.
    for i in rem_a:
        ca = a_clauses[i]
        m = floor_significance(ca.text, "")
        changes.append(
            Change(
                type="REMOVED", significance=_elevate(m.significance), category=m.category,
                title=_title(ca),
                summary="Clause removed in the newer version."
                + (f" Changes: {'; '.join(m.changed_tokens)}." if m.changed_tokens else ""),
                a_text=ca.text, b_text=None,
                a_start=ca.start, a_end=ca.end, b_start=None, b_end=None,
            )
        )
    for j in rem_b:
        cb = b_clauses[j]
        m = floor_significance("", cb.text)
        changes.append(
            Change(
                type="ADDED", significance=_elevate(m.significance), category=m.category,
                title=_title(cb),
                summary="Clause added in the newer version."
                + (f" Changes: {'; '.join(m.changed_tokens)}." if m.changed_tokens else ""),
                a_text=None, b_text=cb.text,
                a_start=None, a_end=None, b_start=cb.start, b_end=cb.end,
            )
        )

    changes.sort(key=lambda c: (c.a_start if c.a_start is not None else 10**9,
                                c.b_start if c.b_start is not None else 10**9))
    return changes


def _modified(ca: Clause, cb: Clause) -> Change:
    m = floor_significance(ca.text, cb.text)
    if m.significance == "COSMETIC":
        return Change(
            type="COSMETIC", significance="COSMETIC", category=m.category,
            title=_title(ca), summary="Wording/formatting only, no material change.",
            a_text=ca.text, b_text=cb.text,
            a_start=ca.start, a_end=ca.end, b_start=cb.start, b_end=cb.end,
        )
    summary = "Clause modified."
    if m.changed_tokens:
        summary = "Changed: " + "; ".join(m.changed_tokens) + "."
    return Change(
        type="MODIFIED", significance=m.significance, category=m.category,
        title=_title(ca), summary=summary,
        a_text=ca.text, b_text=cb.text,
        a_start=ca.start, a_end=ca.end, b_start=cb.start, b_end=cb.end,
    )


def _elevate(sig: str) -> str:
    # Added/removed clauses are never merely cosmetic.
    return "LOW" if sig in ("COSMETIC", "LOW") else sig
