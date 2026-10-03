"""Local, pre-Gemini query guard (Phase 10).

A cheap, deterministic gate that runs BEFORE any retrieval or LLM call so the
system does not spend Gemini requests (or tokens) on input that cannot produce a
useful grounded answer: empty text, keyboard spam/gibberish, greetings, clearly
off-topic chatter, contentless single words, and the same question repeated
inside one message.

Design contract (mirrors the product invariants):
- CONSERVATIVE. When in doubt, classify as ``valid`` and let the existing RAG
  pipeline answer it. A short legal question ("What is the cap?", "Termination?")
  must never be blocked merely for being short.
- NON-INVASIVE. For a valid question the guard returns the ORIGINAL text
  verbatim so retrieval, page parsing, verification and citations are untouched.
  Only the "repeated within one message" case rewrites the query (collapse).
- LOCAL. Every ``local`` decision short-circuits with a friendly message and
  triggers no chunk read and no Gemini call.

This module is pure (no I/O, no DB, no model) so it is trivially unit-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Response copy (surfaced verbatim to the user; no document content involved).
# ---------------------------------------------------------------------------
EMPTY_MESSAGE = "Please enter a question about the selected documents."
GIBBERISH_MESSAGE = (
    "I couldn't understand that. Please ask a question about the selected "
    "contract documents."
)
GREETING_MESSAGE = (
    "Hello! I can help you analyse your selected contract documents — ask about "
    "liability, payment, termination, governing law or risks, or request a "
    "summary or a redline."
)
OFF_TOPIC_MESSAGE = (
    "I'm focused on analysing the selected contract documents. Please ask about "
    "the contract, its clauses, risks, obligations, payments, termination, "
    "liability, or other document content."
)
LOW_INFORMATION_MESSAGE = (
    "Please ask a specific question about the selected documents — for example "
    "liability, payment, termination, governing law, or a summary."
)
REDLINE_UNUSABLE_MESSAGE = (
    "Please describe the contract change you want to make — for example "
    "\u201cchange the liability cap from AED 100,000 to AED 1,000,000\u201d or "
    "\u201cmake the liability clause mutual\u201d."
)

# ---------------------------------------------------------------------------
# Vocabulary. Substring hints (over-matching only causes a ``valid`` outcome,
# which is the safe direction) versus whole-word markers.
# ---------------------------------------------------------------------------
# Contract/domain stems. Presence of any of these means the input is plausibly
# about the documents, so it is never treated as gibberish or off-topic.
_LEGAL_HINTS: tuple[str, ...] = (
    "contract", "agreement", "clause", "liabil", "cap ", " cap", "cap?", "capping",
    "indemn", "warrant", "payment", "pay", "paid", "invoice", "billing", "fee",
    "term", "terminat", "renew", "notice", "insur", "confidential", "breach",
    "governing", "jurisdict", "arbitrat", "disput", "deposit", "retainer",
    "security", "obligat", "responsib", "party", "parties", "supplier",
    "customer", "vendor", "client", "deliver", "service", "scope", "remedy",
    "force majeure", "settle", "signatur", "sign ", "mutual", "deadline",
    "effective date", "termination", "summary", "summariz", "summarise",
    "risk", "compare", "redlin", "redline", "change", "amend", "modif",
    "obligations", "provision", "section", "article", "days", "amount",
    "exceed", "limitation", "exclusi", "license", "ip ownership", "warranty",
)

# Whole-word markers for clearly off-topic (non-contract) chatter.
_OFF_TOPIC_WORDS: frozenset[str] = frozenset({
    "weather", "forecast", "rain", "sunny", "temperature", "cricket", "baseball",
    "football", "soccer", "basketball", "tennis", "game", "games", "match",
    "team", "score", "tournament", "nfl", "nba", "joke", "jokes", "pun",
    "comedy", "recipe", "recipes", "cooking", "ingredient", "bake", "dish",
    "pizza", "restaurant", "movie", "movies", "film", "actor", "actress",
    "song", "songs", "music", "album", "spotify", "netflix", "horoscope",
    "astrology", "celebrity", "birthday", "vacation", "hotel", "flight",
    "trip", "travel", "itinerary", "coding", "code", "python", "javascript",
    "program", "algorithm", "bitcoin", "crypto", "ethereum", "stock", "stocks",
    "meme", "instagram", "tiktok", "twitter", "facebook", "reddit", "homework",
    "essay", "poem", "lyric", "lyrics",
})

# Exact phrases handled as casual chat (answered locally, no Gemini).
_GREETING_PHRASES: frozenset[str] = frozenset({
    "hi", "hii", "hiii", "hello", "helo", "hlo", "hey", "heyy", "hy", "hai",
    "yo", "hiya", "hi there", "hello there", "hey there", "greetings",
    "good morning", "good afternoon", "good evening", "good day",
    "how are you", "how are you doing", "how r u", "hru", "whats up",
    "what is up", "sup", "wassup", "thanks", "thank you", "thankyou", "thx",
    "ty", "tysm", "ok", "okay", "okk", "cool", "nice", "great", "awesome",
    "bye", "goodbye", "good bye", "see you", "cya",
})

# Contentless lone words that cannot form a retrievable question.
_LOW_INFORMATION_LONE: frozenset[str] = frozenset({
    "what", "whats", "who", "when", "where", "why", "how", "which", "whom",
    "whose", "huh", "hm", "hmm", "mm", "pls", "plz", "idk", "i", "it", "this",
    "that", "something", "anything", "stuff", "question",
})

# Common contractions expanded before comparison so "what's the cap" and
# "what is the cap" normalise to the same content signature.
_CONTRACTIONS: dict[str, str] = {
    "what's": "what is", "who's": "who is", "how's": "how is", "it's": "it is",
    "that's": "that is", "there's": "there is", "here's": "here is",
    "let's": "let us", "can't": "can not", "won't": "will not",
    "don't": "do not", "doesn't": "does not", "isn't": "is not",
    "aren't": "are not", "i'm": "i am", "you're": "you are", "we're": "we are",
    "they're": "they are", "i've": "i have", "we've": "we have",
    "they've": "they have", "i'll": "i will", "you'll": "you will",
    "we'll": "we will", "they'll": "they will", "he's": "he is",
    "she's": "she is", "would've": "would have", "should've": "should have",
}

# Stopwords stripped when building a near-duplicate signature (filler only).
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "being", "been", "do",
    "does", "did", "of", "to", "in", "on", "for", "with", "and", "or", "but",
    "if", "so", "as", "at", "by", "from", "this", "that", "these", "those",
    "it", "its", "there", "their", "they", "them", "please", "can", "you",
    "me", "my", "i", "we", "our", "us", "your", "tell", "give", "show", "want",
    "would", "could", "about", "what", "whats", "who", "whom", "whose", "when",
    "where", "why", "how", "which", "any", "some", "hello", "hi", "hey",
    "does", "mean", "say", "says", "said", "has", "have", "had", "not", "no",
    "yes", "just", "also", "then", "than", "into", "out", "up", "down", "over",
})

_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")

_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9']+")
_NON_ALNUM_SPACE_RE = re.compile(r"[^a-z0-9\s]+")


@dataclass(frozen=True)
class GuardResult:
    """Outcome of guarding a chat question.

    ``action`` is ``"local"`` (short-circuit with ``message``; no retrieval /
    Gemini) or ``"continue"`` (feed ``question`` to the existing pipeline).
    ``reason`` is a stable tag for logging/tests: empty | gibberish | greeting |
    off_topic | low_information | collapse | valid.
    """

    action: str
    reason: str
    message: str | None = None
    question: str | None = None

    @property
    def is_local(self) -> bool:
        return self.action == "local"


def _normalize(text: str) -> str:
    """Lowercase, expand contractions, drop punctuation, collapse whitespace."""
    t = (text or "").lower().strip()
    for k, v in _CONTRACTIONS.items():
        t = t.replace(k, v)
    t = _NON_ALNUM_SPACE_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip()


def _has_legal_hint(normalized: str) -> bool:
    padded = f" {normalized} "
    return any(h in padded for h in _LEGAL_HINTS)


def _is_repetitive_junk(word: str) -> bool:
    """True if a short repeating unit covers most of a compact token.

    Catches keyboard-mashing patterns like "sjsjsjsj", "asdasdasd", "zxczxc".
    """
    n = len(word)
    if n < 6:
        return False
    for period in range(1, 5):
        if n < period * 3:
            continue
        unit = word[:period]
        run = 0
        while run < n and word[run] == unit[run % period]:
            run += 1
        if run >= period * 3 and run >= 0.6 * n:
            return True
    return False


def _has_long_char_run(word: str) -> bool:
    """True if one character repeats 4+ times consecutively ("aaaa", "####")."""
    return re.search(r"(.)\1{3,}", word) is not None


def _has_keyboard_row(word: str) -> bool:
    return any(row in word for row in _ROWS)


def _looks_gibberish(text: str, tokens: list[str]) -> bool:
    """Conservative spam detector. Only fires on concrete junk signals."""
    letters = [t for t in tokens if any(c.isalpha() for c in t)]
    if not letters:
        # No alphabetic token at all: symbol-only or digit-only input.
        return True
    non_space = re.sub(r"\s", "", text)
    if non_space:
        alpha = sum(1 for c in non_space if c.isalpha())
        if alpha / len(non_space) < 0.3:
            return True
    for w in letters:
        if _has_keyboard_row(w) or _has_long_char_run(w) or _is_repetitive_junk(w):
            return True
    return False


def _is_greeting(normalized: str) -> bool:
    if normalized in _GREETING_PHRASES:
        return True
    words = set(_WS_RE.split(normalized)) - {""}
    # Only unambiguous greeting/filler words — never interrogatives or content
    # words — so a bare "what"/"who"/"summary" is not treated as a greeting.
    return bool(words) and len(words) <= 4 and words.issubset(_GREETING_TOKENS)


# Curated fallback token pool (kept separate from the phrase list so function
# words such as "what"/"are"/"how" can never trigger a greeting classification).
_GREETING_TOKENS: frozenset[str] = frozenset({
    "hi", "hii", "hiii", "hello", "helo", "hlo", "hey", "heyy", "hy", "hai",
    "yo", "hiya", "greetings", "thanks", "thank", "you", "thx", "ty", "tysm",
    "ok", "okay", "okk", "cool", "nice", "great", "awesome", "bye", "goodbye",
    "cya", "morning", "afternoon", "evening", "good", "day", "there", "welcome",
})


def _is_off_topic(normalized: str, tokens: list[str]) -> bool:
    if _has_legal_hint(normalized):
        return False
    return any(t in _OFF_TOPIC_WORDS for t in tokens)


def _collapse_repetition(stripped: str) -> str | None:
    """Collapse a message that is one question repeated several times.

    "who is that? who is that? who is that?" -> "who is that?"
    Returns None when there is nothing obvious to collapse.
    """
    # Split into segments on question/termination punctuation and newlines.
    segments = [s.strip() for s in re.split(r"[?!\.\n]+", stripped) if s.strip()]
    if len(segments) < 2:
        return None
    norm_segments = [_normalize(s) for s in segments if _normalize(s)]
    if not norm_segments:
        return None
    distinct = set(norm_segments)
    if len(distinct) == 1 and len(norm_segments) >= 2:
        first = segments[0].strip()
        # Preserve the original trailing punctuation style of the first segment.
        tail = ""
        m = re.search(r"([?!])\s*$", stripped)
        if m:
            tail = m.group(1)
        collapsed = first + (tail or "?")
        return collapsed
    return None


def classify_question(text: str) -> GuardResult:
    """Classify a chat question BEFORE any retrieval or LLM call."""
    stripped = (text or "").strip()
    if not stripped:
        return GuardResult("local", "empty", message=EMPTY_MESSAGE)

    collapsed = _collapse_repetition(stripped)
    working = collapsed if collapsed is not None else stripped

    normalized = _normalize(working)
    tokens = _TOKEN_RE.findall(normalized)
    has_legal = _has_legal_hint(normalized)

    if not has_legal and _is_greeting(normalized):
        return GuardResult("local", "greeting", message=GREETING_MESSAGE)

    if not has_legal and _looks_gibberish(working, tokens):
        return GuardResult("local", "gibberish", message=GIBBERISH_MESSAGE)

    if _is_off_topic(normalized, tokens):
        return GuardResult("local", "off_topic", message=OFF_TOPIC_MESSAGE)

    if (
        not has_legal
        and len(tokens) == 1
        and normalized in _LOW_INFORMATION_LONE
    ):
        return GuardResult("local", "low_information", message=LOW_INFORMATION_MESSAGE)

    # Not collapsed -> pass the ORIGINAL user text so the pipeline is untouched.
    if collapsed is not None:
        return GuardResult("continue", "collapse", question=collapsed)
    return GuardResult("continue", "valid", question=text)


def question_signature(text: str) -> str:
    """Stable near-duplicate key: content words only, sorted, stemmed-ish.

    Two questions sharing a signature are treated as the same query for the
    purpose of safe answer reuse (which also requires an identical document
    scope). Empty signature (no content words) means "never reuse".
    """
    normalized = _normalize(text)
    if _has_legal_hint(normalized) is False and not _TOKEN_RE.findall(normalized):
        return ""
    words: list[str] = []
    for tok in _TOKEN_RE.findall(normalized):
        if tok in _STOPWORDS:
            continue
        # Light plural normalisation so "caps"/"cap" and "clauses"/"clause" match.
        if len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        words.append(tok)
    if not words:
        return ""
    return "|".join(sorted(set(words)))


def _has_explicit_replacement(normalized: str) -> bool:
    """Detect a concrete from->to style edit even without a domain keyword."""
    return bool(
        re.search(r"\bfrom\b.+\bto\b", normalized)
        or re.search(r"\b(?:change|replace|set|update)\b.+\bto\b", normalized)
        or re.search(r"(?:aed|usd|\$|€|£|eur)\s*\d", normalized)
    )


def is_usable_redline_instruction(text: str) -> bool:
    """Guard for redline instructions: reject only obviously-unusable input.

    Empty/whitespace, pure gibberish and vague target-less chatter ("change",
    "make it better", "do something") return False so no Gemini is spent. A
    usable instruction must point at something in the contract — either a domain
    anchor (liability, cap, payment, clause, term, mutual, days, ...) or an
    explicit from->to / currency replacement. Legitimate semantic edits such as
    "make the liability clause more balanced" (which carry no exact value) still
    pass, so the redline safety pipeline is never bypassed.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    normalized = _normalize(stripped)
    tokens = _TOKEN_RE.findall(normalized)
    if not tokens:
        return False
    has_legal = _has_legal_hint(normalized)
    if _looks_gibberish(stripped, tokens) and not has_legal:
        return False
    # A lone vague verb with no target is unusable ("change", "edit", "fix").
    if len(tokens) == 1 and normalized in {"change", "edit", "fix", "modify",
                                           "update", "improve", "adjust", "rewrite"}:
        return False
    # Otherwise require a contract anchor or a concrete replacement signal.
    return has_legal or _has_explicit_replacement(normalized)
