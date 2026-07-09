"""Statement advising module (#56).

Heuristic, deterministic, server-side quality checks for draft Polis statements.
No external calls, no LLM, no privacy surface: the draft text never leaves the
process. Each check returns a :class:`Flag`; the module *advises* and never blocks
submission — callers decide what to do with the flags.

The checks intentionally favour precision over recall: a false positive (nagging a
fine statement) is more harmful to trust than a missed compound, so each heuristic
is conservative. See issue #56 for the principles (atomicity, neutrality,
concreteness, scope, statement form) and their literature basis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class CheckId(str, Enum):
    ATOMICITY = "atomicity"
    NEUTRALITY = "neutrality"
    CONCRETENESS = "concreteness"
    SCOPE = "scope"
    FORM = "form"


class Severity(str, Enum):
    OK = "ok"
    WARN = "warn"


@dataclass(frozen=True)
class Flag:
    check: CheckId
    severity: Severity
    message: str

    def to_dict(self) -> dict:
        return {"check": self.check.value, "severity": self.severity.value, "message": self.message}


@dataclass(frozen=True)
class Advice:
    """Result of advising on one draft statement."""
    flags: tuple[Flag, ...]

    @property
    def warnings(self) -> list[Flag]:
        return [f for f in self.flags if f.severity is Severity.WARN]

    @property
    def ok(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict:
        return {"ok": self.ok, "flags": [f.to_dict() for f in self.flags]}


# ── Heuristic vocabularies ──────────────────────────────────────────────────
# Modal/verb cues that mark a clause as carrying a *claim* (used to tell a real
# compound apart from an innocuous noun-list "and").
_CLAIM_CUES = re.compile(
    r"\b(should|must|ought|shall|needs?\s+to|has\s+to|have\s+to|is|are|was|were|"
    r"will|won't|can|cannot|can't|requires?|disclose[sd]?|publish(?:es|ed)?|"
    r"allow[sed]*|ban[sned]*|provide[sd]?|ensure[sd]?)\b",
    re.IGNORECASE,
)
# Coordinating/subordinating cues that can join two independent claims.
_COMPOUND_SPLIT = re.compile(r"\b(and|but|because|whereas|while|;)\b", re.IGNORECASE)

# Loaded / evaluative language that biases toward an answer (neutrality).
_LOADED_TERMS = {
    "unjustly", "unfairly", "obviously", "clearly", "ridiculous", "absurd",
    "corrupt", "bureaucratic", "broken", "toxic", "outrageous", "shameful",
    "disgraceful", "silences", "silencing", "destroys", "destroying", "evil",
    "stupid", "idiotic", "blatant", "blatantly", "egregious",
}
# Vague aspiration cues with no falsifiable content (concreteness).
_VAGUE_TERMS = {
    "better", "healthier", "healthy", "good", "great", "nicer", "improved",
    "improve", "inclusive", "welcoming", "stronger", "more", "less",
}
# Absolute quantifiers that usually over-broaden a claim (scope).
_ABSOLUTE_TERMS = {
    "all", "every", "everyone", "everybody", "always", "never", "none",
    "nobody", "no one", "any", "anything", "nothing",
}
_QUESTION_OPENERS = (
    "shouldn't", "should", "is", "are", "do", "does", "can", "could", "would",
    "why", "how", "what", "who", "when", "where", "isn't", "aren't", "don't",
    "doesn't", "wouldn't", "couldn't",
)


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _check_form(text: str, words: list[str]) -> Flag:
    stripped = text.strip()
    if stripped.endswith("?"):
        return Flag(CheckId.FORM, Severity.WARN,
                    "This reads as a question. Rewrite it as a claim participants can agree or disagree with.")
    # A title/topic fragment: no claim cue and very short.
    if words and not _CLAIM_CUES.search(text) and len(words) <= 4:
        return Flag(CheckId.FORM, Severity.WARN,
                    "This looks like a topic or title rather than a claim. State a position.")
    return Flag(CheckId.FORM, Severity.OK, "Reads as a statement.")


def _check_atomicity(text: str) -> Flag:
    # Compound only when a joining word separates two claim-bearing clauses.
    parts = _COMPOUND_SPLIT.split(text)
    if len(parts) < 3:
        return Flag(CheckId.ATOMICITY, Severity.OK, "Single claim.")
    # parts alternates [segment, joiner, segment, joiner, ...]
    segments = parts[0::2]
    claim_segments = [s for s in segments if _CLAIM_CUES.search(s)]
    if len(claim_segments) >= 2:
        return Flag(CheckId.ATOMICITY, Severity.WARN,
                    "This may contain more than one claim. If so, split it into separate statements.")
    return Flag(CheckId.ATOMICITY, Severity.OK, "Single claim.")


def _check_neutrality(text: str, words: list[str]) -> Flag:
    hits = sorted({w for w in words if w in _LOADED_TERMS})
    if hits:
        return Flag(CheckId.NEUTRALITY, Severity.WARN,
                    f"Loaded phrasing ({', '.join(hits)}) may push toward an answer. Describe the situation neutrally.")
    return Flag(CheckId.NEUTRALITY, Severity.OK, "Phrasing reads neutral.")


def _check_concreteness(text: str, words: list[str]) -> Flag:
    has_vague = any(w in _VAGUE_TERMS for w in words)
    has_concrete = bool(re.search(r"\d", text)) or len(words) >= 12
    if has_vague and not has_concrete:
        return Flag(CheckId.CONCRETENESS, Severity.WARN,
                    "This is fairly vague. Name a specific mechanism, action, or consequence.")
    return Flag(CheckId.CONCRETENESS, Severity.OK, "Specific enough.")


def _check_scope(text: str, words: list[str]) -> Flag:
    joined = " " + " ".join(words) + " "
    hits = sorted({t for t in _ABSOLUTE_TERMS if f" {t} " in joined})
    if hits:
        return Flag(CheckId.SCOPE, Severity.WARN,
                    f"Absolute wording ({', '.join(hits)}) is often too broad. Consider narrowing the claim.")
    return Flag(CheckId.SCOPE, Severity.OK, "Scope looks reasonable.")


def advise(text: str) -> Advice:
    """Run all quality checks on a draft statement and return structured advice."""
    text = (text or "").strip()
    words = _words(text)
    if not words:
        return Advice(flags=(Flag(CheckId.FORM, Severity.WARN, "Empty statement."),))
    flags = (
        _check_form(text, words),
        _check_atomicity(text),
        _check_neutrality(text, words),
        _check_concreteness(text, words),
        _check_scope(text, words),
    )
    return Advice(flags=flags)
