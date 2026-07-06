"""Tests for the statement advising module (#56).

The examples are drawn directly from the issue's good/bad cases so the heuristics
stay anchored to the documented intent.
"""
from statement_advisor import CheckId, Severity, advise


def _warned(advice, check: CheckId) -> bool:
    return any(f.check is check and f.severity is Severity.WARN for f in advice.flags)


# ── Good statements should pass cleanly ─────────────────────────────────────

def test_good_statement_is_clean():
    advice = advise(
        "The Wikimedia Foundation should publish a detailed annual report on how "
        "discretionary grants are allocated."
    )
    assert advice.ok, advice.to_dict()


def test_good_specific_policy_claim_clean():
    advice = advise("Editors should be required to disclose paid contributions on their user page.")
    assert advice.ok, advice.to_dict()


# ── Atomicity (compound claims) ─────────────────────────────────────────────

def test_compound_two_claims_flagged():
    advice = advise(
        "Wikipedia should require reliable sources and editors should disclose "
        "conflicts of interest."
    )
    assert _warned(advice, CheckId.ATOMICITY)


def test_noun_list_and_is_not_compound():
    # The issue's named false-positive case: syntactic "and", single claim.
    advice = advise("Wikipedia and Wikimedia are both affected by declining editor retention.")
    assert not _warned(advice, CheckId.ATOMICITY), advice.to_dict()


# ── Statement form (questions / titles) ─────────────────────────────────────

def test_question_form_flagged():
    advice = advise("Shouldn't the Wikimedia Foundation be more transparent?")
    assert _warned(advice, CheckId.FORM)


def test_title_fragment_flagged():
    advice = advise("Editor retention")
    assert _warned(advice, CheckId.FORM)


# ── Neutrality (loaded language) ────────────────────────────────────────────

def test_loaded_language_flagged():
    advice = advise(
        "Wikipedia's bureaucratic deletion process unjustly silences new editors."
    )
    assert _warned(advice, CheckId.NEUTRALITY)


# ── Concreteness (vague aspirations) ────────────────────────────────────────

def test_vague_aspiration_flagged():
    advice = advise("Wikimedia should have a healthier community.")
    assert _warned(advice, CheckId.CONCRETENESS)


def test_vague_things_should_be_better_flagged():
    advice = advise("Things should be better.")
    assert _warned(advice, CheckId.CONCRETENESS)


# ── Scope (absolutes) ───────────────────────────────────────────────────────

def test_absolute_scope_flagged():
    advice = advise("Every article must always cite at least three independent sources.")
    assert _warned(advice, CheckId.SCOPE)


# ── Shape of the result ─────────────────────────────────────────────────────

def test_empty_statement_warns_form():
    advice = advise("   ")
    assert _warned(advice, CheckId.FORM)


def test_to_dict_is_serialisable():
    d = advise("Editors should disclose paid contributions.").to_dict()
    assert set(d) == {"ok", "flags"}
    assert all(set(f) == {"check", "severity", "message"} for f in d["flags"])
