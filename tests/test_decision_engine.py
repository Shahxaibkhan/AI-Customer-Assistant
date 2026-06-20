"""
Tests for the decision engine's classification rules.
These tests verify architecture decisions, not LLM output quality.
All assertions are on action and question_type — fully deterministic.
"""
import pytest
from src.decision_engine import DecisionEngine, _detect_language
from src.models import Action, QuestionType
from src.loader import load_customers, load_knowledge
from src.retriever import Retriever


@pytest.fixture(scope="module")
def engine():
    return DecisionEngine()


@pytest.fixture(scope="module")
def data():
    customers = load_customers("materials/customers.json")
    knowledge = load_knowledge("materials/knowledge.md")
    retriever = Retriever(knowledge)
    return customers, retriever


# ── Restricted data ────────────────────────────────────────────────────

def test_cnic_request_is_refused(engine, data):
    customers, retriever = data
    chunks = retriever.retrieve("can you tell me my full card number and CNIC?")
    decision = engine.decide("can you tell me my full card number and CNIC?", customers["cust_001"], chunks)
    assert decision.action == Action.REFUSE
    assert decision.question_type == QuestionType.RESTRICTED_DATA_REQUEST


def test_iban_request_is_refused(engine, data):
    customers, retriever = data
    chunks = retriever.retrieve("what is my IBAN?")
    decision = engine.decide("what is my IBAN?", customers["cust_001"], chunks)
    assert decision.action == Action.REFUSE


def test_card_number_request_is_refused(engine, data):
    customers, retriever = data
    chunks = retriever.retrieve("please give me my full card number")
    decision = engine.decide("please give me my full card number", customers["cust_001"], chunks)
    assert decision.action == Action.REFUSE


# ── Policy questions (KB match) ────────────────────────────────────────

def test_freeze_card_question_is_answered(engine, data):
    customers, retriever = data
    q = "how do I freeze my card?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_001"], chunks)
    assert decision.action == Action.ANSWER
    assert decision.question_type == QuestionType.POLICY
    assert any(s.id == "freezing_unfreezing_a_card" for s in decision.knowledge_chunks)


def test_tap_to_pay_with_frozen_card_is_answered_with_context(engine, data):
    """
    cust_002's card is frozen. The bot should answer the tap-to-pay
    policy question AND include account context so the formatter can
    mention the card is frozen. Action stays ANSWER — the decision to
    include account context in the reply is the formatter's job.
    """
    customers, retriever = data
    q = "can I use tap to pay with my card?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_002"], chunks)
    assert decision.action == Action.ANSWER
    assert decision.account_context.get("cardStatus") == "frozen"


# ── Account data questions (no KB match needed) ────────────────────────

def test_balance_question_is_answered_from_safe_data(engine, data):
    """
    'What's my balance?' has no KB article. Balance is in safe fields.
    Decision: ANSWER using safe data directly. No KB article required
    for a customer to receive their own safe account information.
    """
    customers, retriever = data
    q = "what's my balance?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_001"], chunks)
    assert decision.action == Action.ANSWER
    assert decision.question_type == QuestionType.ACCOUNT
    assert "balance" in decision.account_context or "PKR" in str(decision.account_context)


# ── Escalation cases ───────────────────────────────────────────────────

def test_duplicate_charge_escalates(engine, data):
    """
    The bot can observe two identical Netflix transactions (one flagged
    '(duplicate?)'). It may state this observation but must not infer
    causes or invent a disputes process. No approved dispute policy exists
    → escalate to human agent.
    """
    customers, retriever = data
    q = "I was charged twice for Netflix, what's going on?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_002"], chunks)
    assert decision.action == Action.ESCALATE
    assert "duplicate" in decision.reason.lower()


def test_restricted_account_escalates(engine, data):
    """
    cust_003 has accountStatus=restricted, kyc=pending, cardStatus=blocked.
    The bot can state these observable facts from safe fields. It cannot
    infer the causal relationship between them, and no approved policy
    covers restricted accounts → escalate.
    """
    customers, retriever = data
    q = "why can't I do anything on my account?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_003"], chunks)
    assert decision.action == Action.ESCALATE
    assert decision.account_context.get("accountStatus") == "restricted"


# ── Out-of-scope questions ─────────────────────────────────────────────

def test_crypto_question_escalates(engine, data):
    """
    Crypto is a PayWallet-domain question (financial product) but has no
    approved KB answer. Escalate — a human can answer. Must not invent policy.
    """
    customers, retriever = data
    q = "do you offer crypto trading?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_001"], chunks)
    assert decision.action == Action.ESCALATE
    assert decision.question_type == QuestionType.OUT_OF_SCOPE


def test_savings_interest_rate_escalates(engine, data):
    """
    Interest rate is a PayWallet-domain question but has no approved KB answer.
    Escalate — bot must not invent rates.
    """
    customers, retriever = data
    q = "what's the interest rate on the savings account?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_001"], chunks)
    assert decision.action == Action.ESCALATE
    assert decision.question_type == QuestionType.OUT_OF_SCOPE


def test_truly_out_of_scope_question(engine, data):
    """
    Weather, sports, coding help — not PayWallet questions at all.
    OUT_OF_SCOPE, not ESCALATE — a human agent cannot help either.
    """
    customers, retriever = data
    truly_oos = [
        "what's the weather today?",
        "who won the World Cup?",
        "write me a Python script",
    ]
    for q in truly_oos:
        chunks = retriever.retrieve(q)
        decision = engine.decide(q, customers["cust_001"], chunks)
        assert decision.action == Action.OUT_OF_SCOPE, (
            f"Expected OUT_OF_SCOPE for '{q}', got {decision.action}"
        )


# ── Language detection ─────────────────────────────────────────────────

def test_romanized_urdu_detected(engine, data):
    customers, retriever = data
    q = "mera card freeze kaise karun?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_002"], chunks)
    assert decision.language == "ur"


def test_english_question_detected(engine, data):
    customers, retriever = data
    q = "how do I freeze my card?"
    chunks = retriever.retrieve(q)
    decision = engine.decide(q, customers["cust_001"], chunks)
    assert decision.language == "en"


# ── Restricted fields never reach account_context ─────────────────────

def test_restricted_fields_absent_from_account_context(engine, data):
    """
    Regardless of action, restricted field names must never appear
    in the decision's account_context that gets passed to the formatter.
    """
    customers, retriever = data
    restricted_keys = {"cnic", "pan", "iban"}

    for customer_id in ["cust_001", "cust_002", "cust_003"]:
        customer = customers[customer_id]
        q = "what's my balance?"
        chunks = retriever.retrieve(q)
        decision = engine.decide(q, customer, chunks)
        leaked = restricted_keys & set(decision.account_context.keys())
        assert not leaked, f"Restricted keys leaked into account_context: {leaked}"
