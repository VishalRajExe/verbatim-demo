"""Real DOCX tracked changes via low-level OOXML (Architecture §11, Part C).

python-docx has no first-class tracked-changes API, so we edit the underlying
lxml tree directly and emit spec-correct ``<w:ins>`` / ``<w:del>`` elements with
``<w:delText>``. The engine splits runs so a target that spans multiple runs
(e.g. a phrase broken by formatting) still becomes a single clean revision, and
paragraphs we never touch are left byte-identical.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass
class AppliedEdit:
    target: str
    replacement: str
    paragraph_index: int
    revision_id: int


def _para_text(p) -> str:
    """Concatenated text of a paragraph's runs (only the plain ``w:t`` text)."""
    return "".join(t.text or "" for r in p.findall(qn("w:r")) for t in r.findall(qn("w:t")))


def _iter_paragraphs(document: Document) -> list[Paragraph]:
    """Every paragraph in the document body, in reading order, INCLUDING the
    paragraphs that live inside tables.

    ``document.paragraphs`` returns only top-level body paragraphs and silently
    omits table cells, so a value that appears only in a table (fee schedules,
    notice periods, escalation targets ...) would be invisible to verification
    and un-editable - the redline would then check a *different, incomplete*
    view of the file than the one the viewer/extractor and the RAG text show.
    Walking every ``w:p`` under the body keeps the run tree the redline edits in
    sync with the content that is actually displayed, for any DOCX."""
    body = document.element.body
    return [Paragraph(p, document) for p in body.iter(qn("w:p"))]


def _make(tag: str, parent, **attrib):
    el = parent.makeelement(qn(tag), {})
    for k, v in attrib.items():
        el.set(qn(k), v)
    parent.append(el)
    return el


def _run_text(run):
    ts = run.findall(qn("w:t"))
    return "".join(t.text or "" for t in ts)


def _split_run(run: "object", offset: int):
    """Split a run at a character offset into (before, after) run elements.

    Returns (left_run, right_run). Both keep the original run properties.
    """
    text = _run_text(run)
    if offset <= 0 or offset >= len(text):
        return None, None
    left = copy.deepcopy(run)
    right = copy.deepcopy(run)
    _set_run_text(left, text[:offset])
    _set_run_text(right, text[offset:])
    parent = run.getparent()
    idx = list(parent).index(run)
    parent.remove(run)
    parent.insert(idx, left)
    parent.insert(idx + 1, right)
    return left, right


def _set_run_text(run, text: str):
    # Drop all but the first w:t, set its text, preserve xml:space.
    ts = run.findall(qn("w:t"))
    for extra in ts[1:]:
        run.remove(extra)
    if not ts:
        t = run.makeelement(qn("w:t"), {})
        run.append(t)
        ts = [t]
    t = ts[0]
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _runs_of(p):
    return p.findall(qn("w:r"))


def find_paragraph_with_target(document: Document, target: str) -> tuple[int, Paragraph] | tuple[None, None]:
    for i, para in enumerate(_iter_paragraphs(document)):
        if target in _para_text(para._p):
            return i, para
    return None, None


def _paragraph_for_target(
    document: Document, target: str, context: str
) -> tuple[int, Paragraph] | tuple[None, None]:
    """Pick the paragraph to edit.

    When the target is globally unique that is the paragraph. When it repeats,
    a verbatim ``context`` passage that occurs exactly once and contains the
    target pins the single intended paragraph; otherwise nothing is chosen (the
    caller drops the edit rather than guessing an occurrence).
    """
    if count_occurrences(document, target) == 1:
        return find_paragraph_with_target(document, target)
    if context:
        hits = [
            (i, para)
            for i, para in enumerate(_iter_paragraphs(document))
            if context in _para_text(para._p) and target in _para_text(para._p)
        ]
        if len(hits) == 1:
            return hits[0]
    return None, None


def count_occurrences(document: Document, target: str) -> int:
    total = 0
    for para in _iter_paragraphs(document):
        total += _para_text(para._p).count(target)
    return total


def paragraph_texts(document: Document) -> list[str]:
    """Plain text of every paragraph, from the same run-joined source that
    ``count_occurrences`` matches against. Callers use these as verbatim context
    anchors, so the strings must be consistent with the uniqueness check."""
    return [_para_text(para._p) for para in _iter_paragraphs(document)]


def apply_tracked_edit(
    document: Document,
    target: str,
    replacement: str,
    author: str = "Legal AI",
    timestamp: datetime | None = None,
    context: str = "",
) -> AppliedEdit:
    """Wrap ``target`` in ``w:del`` and insert ``replacement`` as ``w:ins``.

    Requires the target to resolve to exactly one location: either it occurs once
    in the document, or a unique ``context`` passage pins which of several
    occurrences is meant. Raises ValueError otherwise so the caller can report
    the dropped edit honestly.
    """
    if not target:
        raise ValueError("Edit target is empty.")
    occ = count_occurrences(document, target)
    if occ == 0:
        raise ValueError("Edit target not found.")
    idx, para = _paragraph_for_target(document, target, context)
    if para is None:
        if occ > 1:
            raise ValueError(
                "Edit target appears more than once (not exactly once); provide "
                "unique surrounding context to disambiguate."
            )
        raise ValueError("Edit target not found.")

    p = para._p
    full = _para_text(p)
    start = full.find(target)
    end = start + len(target)

    # 1. Split runs at the start and end boundaries so the target is a clean
    #    set of whole runs.
    _split_at(p, start)
    _split_at(p, end)

    # 2. Re-walk runs and collect those fully inside [start, end).
    runs = _runs_of(p)
    covered: list = []
    pos = 0
    for r in runs:
        rt = _run_text(r)
        rstart, rend = pos, pos + len(rt)
        if rt and rstart >= start and rend <= end:
            covered.append(r)
        pos = rend
    if not covered:
        raise ValueError("Edit target spans no runs (unexpected structure).")

    timestamp = timestamp or datetime.now(timezone.utc)
    date_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    rev_id = _next_revision_id(p)

    anchor = covered[0]
    parent = anchor.getparent()
    insert_index = list(parent).index(anchor)

    # 3. Build the <w:del> preserving each covered run's formatting.
    del_el = parent.makeelement(qn("w:del"), {})
    del_el.set(qn("w:id"), str(rev_id))
    del_el.set(qn("w:author"), author)
    del_el.set(qn("w:date"), date_str)
    for r in covered:
        dr = copy.deepcopy(r)
        for t in dr.findall(qn("w:t")):
            t.tag = qn("w:delText")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        parent.remove(r)
        del_el.append(dr)

    # 4. Build the <w:ins> with the replacement text, cloning run props.
    ins_el = parent.makeelement(qn("w:ins"), {})
    ins_el.set(qn("w:id"), str(rev_id + 1))
    ins_el.set(qn("w:author"), author)
    ins_el.set(qn("w:date"), date_str)
    ins_run = ins_el.makeelement(qn("w:r"), {})
    src_rpr = covered[0].find(qn("w:rPr"))
    if src_rpr is not None:
        ins_run.append(copy.deepcopy(src_rpr))
    ins_t = ins_run.makeelement(qn("w:t"), {})
    ins_t.text = replacement
    ins_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    ins_run.append(ins_t)
    ins_el.append(ins_run)

    parent.insert(insert_index, del_el)
    parent.insert(insert_index + 1, ins_el)

    return AppliedEdit(target=target, replacement=replacement,
                       paragraph_index=idx, revision_id=rev_id)


def _split_at(p, offset: int):
    """Ensure a run boundary exists exactly at ``offset`` in paragraph ``p``."""
    pos = 0
    for r in _runs_of(p):
        rt = _run_text(r)
        rstart, rend = pos, pos + len(rt)
        if rstart < offset < rend:
            _split_run(r, offset - rstart)
            return
        pos = rend


def _next_revision_id(p) -> int:
    ids = [int(e.get(qn("w:id"))) for e in p.iter() if e.get(qn("w:id"))]
    ids = [i for i in ids if str(i).lstrip("-").isdigit()]
    return (max(ids) + 1) if ids else 1001


def count_tracked_changes(xml_bytes: bytes) -> tuple[int, int]:
    """Count ``w:ins`` and ``w:del`` elements in a saved document.xml."""
    from lxml import etree
    import zipfile
    import io

    with zipfile.ZipFile(io.BytesIO(xml_bytes)) as z:
        data = z.read("word/document.xml")
    root = etree.fromstring(data)
    ins = len(root.findall(f".//{{{W}}}ins"))
    dele = len(root.findall(f".//{{{W}}}del"))
    return ins, dele
