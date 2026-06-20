"""
Tests that the retriever maps questions to the correct KB sections.
Uses real KB content — retrieval correctness is deterministic and testable.
"""
from src.retriever import Retriever


def test_freeze_question_matches_freeze_section(knowledge):
    r = Retriever(knowledge)
    results = r.retrieve("how do I freeze my card?")
    assert results, "Expected at least one KB match"
    assert results[0].id == "freezing_unfreezing_a_card"


def test_tap_to_pay_question_matches_tap_section(knowledge):
    r = Retriever(knowledge)
    results = r.retrieve("can I use tap to pay with my card?")
    assert results
    assert results[0].id == "tap_to_pay"


def test_romanized_urdu_freeze_question_matches_freeze_section(knowledge):
    r = Retriever(knowledge)
    results = r.retrieve("mera card freeze kaise karun?")
    assert results
    assert results[0].id == "freezing_unfreezing_a_card"


def test_crypto_question_matches_nothing(knowledge):
    r = Retriever(knowledge)
    results = r.retrieve("do you offer crypto trading?")
    assert results == [], "Crypto is not in the KB — should return empty"


def test_interest_rate_question_matches_nothing(knowledge):
    r = Retriever(knowledge)
    results = r.retrieve("what's the interest rate on the savings account?")
    assert results == [], "Savings/interest rate is not in the KB"
