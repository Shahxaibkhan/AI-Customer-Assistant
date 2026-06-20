import re
from .models import Action, QuestionType, Decision, Customer, KnowledgeSection
from .logger import get_logger

log = get_logger()


# Fields the customer must never receive, regardless of how they ask.
# These match the "restricted" keys in customers.json.
_RESTRICTED_TRIGGERS = [
    "cnic", "national id", "id number", "national identity",
    "card number", "full card", "pan number",
    "iban", "account number",
    "card details", "card info", "card data",
]

# Questions about the customer's own account data (not product policy).
# Safe fields can answer these directly without a KB article.
_ACCOUNT_DATA_TRIGGERS = [
    "balance", "how much", "transaction", "statement", "history",
    "account status", "card status", "kyc", "recent", "charged",
    "charge", "why can't", "why cant", "anything on my",
    "is my card", "my account", "my balance", "my transactions",
    # personal info — firstName is a safe field
    "my name", "what is my name", "who am i",
    # payment inability — cardStatus answers this directly
    "not able to pay", "cannot pay", "can't pay", "unable to pay",
    "what am i not able", "payment not going", "why can't i pay",
]

# Keywords that indicate a question is specifically about transactions/charges.
# Used to scope duplicate-transaction escalation — a frozen card question
# should not escalate just because the same customer has a flagged transaction.
_TRANSACTION_PROBLEM_TRIGGERS = [
    "charged", "charge", "transaction", "deducted", "debited",
    "netflix", "duplicate", "twice", "double", "same amount",
]

# Questions that are PayWallet-domain questions even if no KB article exists.
# These escalate (a human agent can answer) rather than returning OUT_OF_SCOPE.
# Distinct from truly irrelevant questions (weather, sports, coding help).
_PAYWALLET_DOMAIN_KEYWORDS = [
    # account & wallet
    "account", "savings", "wallet", "paywallet",
    # card
    "card", "debit", "virtual card", "physical card",
    # payments & transfers
    "payment", "transfer", "send", "receive", "pay", "international",
    # financial products
    "interest", "rate", "fee", "loan", "crypto", "trading",
    "invest", "withdraw", "deposit", "limit",
    # identity & service
    "kyc", "verify", "verification", "support", "service",
]


class DecisionEngine:
    """
    Pure decision logic. No LLM calls. Given a question, customer record,
    and retrieved KB chunks, returns a Decision with action + full context
    for the formatter.

    Two data sources exist and are treated differently:
      - Policy questions  → require a KB match
      - Account questions → answered from safe customer fields directly
      - Restricted        → refused at all times
      - Ambiguous/none    → escalated
    """

    def decide(
        self,
        question: str,
        customer: Customer,
        knowledge_chunks: list,
    ) -> Decision:
        decision = self._decide(question, customer, knowledge_chunks)
        log.info(
            f"DECIDE  '{question}'  customer={customer.safe.first_name}"
            f"  → {str(decision.action).split('.')[-1].upper()}"
            f"  reason={decision.reason}"
        )
        return decision

    def _decide(
        self,
        question: str,
        customer: Customer,
        knowledge_chunks: list,
    ) -> Decision:
        language = _detect_language(question)
        q = question.lower()

        # ── Rule 1: Restricted data request ─────────────────────────────
        # Highest priority. Checked before anything else so a restricted
        # request can never slip through via a KB match.
        if self._is_restricted_request(q):
            return Decision(
                action=Action.REFUSE,
                question_type=QuestionType.RESTRICTED_DATA_REQUEST,
                reason=(
                    "Customer requested a restricted field (CNIC, card number, or IBAN). "
                    "These must never appear in a reply."
                ),
                account_context=customer.safe.to_dict(),
                customer_first_name=customer.safe.first_name,
                language=language,
                original_question=question,
            )

        # ── Rule 2: KB match exists ──────────────────────────────────────
        # Answer with the matched policy. Enrich with safe account context
        # when it materially affects the answer (e.g. card is frozen when
        # asking about tap to pay). The formatter decides what to include.
        if knowledge_chunks:
            return Decision(
                action=Action.ANSWER,
                question_type=QuestionType.POLICY,
                reason="Matched approved KB content.",
                knowledge_chunks=knowledge_chunks,
                account_context=customer.safe.to_dict(),
                customer_first_name=customer.safe.first_name,
                language=language,
                original_question=question,
            )

        # ── Rule 3: Account data question (no KB match) ──────────────────
        # Balance, transaction history, card/account status are safe fields
        # and can be shared directly. No KB article is required for a
        # customer to receive their own safe data.
        if self._is_account_data_question(q):
            problem = self._detect_visible_problem(customer, q)
            if problem:
                # Bot observes the facts but has no approved resolution path.
                # Report observations only; escalate for next steps.
                return Decision(
                    action=Action.ESCALATE,
                    question_type=QuestionType.ACCOUNT,
                    reason=(
                        f"Observable account state: {problem}. "
                        "No approved policy exists for resolution — escalating to human agent."
                    ),
                    account_context=customer.safe.to_dict(),
                    customer_first_name=customer.safe.first_name,
                    language=language,
                    original_question=question,
                )
            # No problem detected — answer with safe data.
            return Decision(
                action=Action.ANSWER,
                question_type=QuestionType.ACCOUNT,
                reason="Account data question answered from safe customer fields.",
                account_context=customer.safe.to_dict(),
                customer_first_name=customer.safe.first_name,
                language=language,
                original_question=question,
            )

        # ── Rule 4: PayWallet-related, but no approved KB content ───────────
        # The question is about the product or company (payments, savings,
        # interest rates, crypto, etc.) but the bot has no approved answer.
        # A human agent can answer — escalate rather than dismiss.
        if self._is_paywallet_related(q):
            return Decision(
                action=Action.ESCALATE,
                question_type=QuestionType.OUT_OF_SCOPE,
                reason=(
                    "PayWallet-related question but no approved KB content. "
                    "Bot must not invent policy — escalating to human agent."
                ),
                account_context=customer.safe.to_dict(),
                customer_first_name=customer.safe.first_name,
                language=language,
                original_question=question,
            )

        # ── Rule 5: Truly out of scope ───────────────────────────────────────
        # Not a PayWallet support request at all (weather, sports, coding, etc.)
        # A human agent cannot help either — no escalation needed.
        return Decision(
            action=Action.OUT_OF_SCOPE,
            question_type=QuestionType.OUT_OF_SCOPE,
            reason="Not a PayWallet support request.",
            customer_first_name=customer.safe.first_name,
            language=language,
            original_question=question,
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_restricted_request(q: str) -> bool:
        return any(trigger in q for trigger in _RESTRICTED_TRIGGERS)

    @staticmethod
    def _is_account_data_question(q: str) -> bool:
        return any(trigger in q for trigger in _ACCOUNT_DATA_TRIGGERS)

    @staticmethod
    def _is_paywallet_related(q: str) -> bool:
        return any(kw in q for kw in _PAYWALLET_DOMAIN_KEYWORDS)

    @staticmethod
    def _detect_visible_problem(customer: Customer, question: str) -> str:
        """
        Returns a description of observable account problems, or empty string.
        The bot may state these facts but must not infer causes between them.

        The duplicate-transaction check is scoped to questions actually about
        transactions or charges. A frozen-card question should not escalate just
        because the same customer has a flagged transaction — those are separate issues.

        Note: in production, duplicate detection would be a proper boolean field
        from the transaction service (e.g. is_flagged=true), not a string annotation.
        """
        problems = []

        # Duplicate transaction — only relevant when question is about charges/transactions.
        # Detects the "(duplicate?)" annotation in the transaction string as provided by
        # the data source. In production the owning service would expose a typed field
        # (e.g. is_flagged: bool) — the detection logic would be identical, just cleaner.
        txns = customer.safe.recent_transactions
        flagged = [t for t in txns if "duplicate?" in t.lower()]
        if flagged and any(kw in question for kw in _TRANSACTION_PROBLEM_TRIGGERS):
            problems.append(
                f"transaction flagged as possible duplicate: '{flagged[0]}'"
            )

        # Account restriction — affects everything, always surface it.
        _PROBLEM_STATUSES = {"restricted", "suspended", "blocked", "frozen"}
        if customer.safe.account_status in _PROBLEM_STATUSES:
            problems.append(
                f"account status is {customer.safe.account_status} "
                f"and KYC is {customer.safe.kyc}"
            )

        return "; ".join(problems)


def _detect_language(text: str) -> str:
    """
    Returns 'ur' for Urdu (script or common romanized), 'en' otherwise.
    Romanized Urdu (Latin-script Urdu) is common in Pakistan and must be
    matched so the formatter responds in the same register.
    """
    # Urdu Unicode script
    if re.search(r'[؀-ۿ]', text):
        return "ur"

    # Common romanized Urdu words
    romanized = {"mera", "meri", "karo", "kaise", "karun", "aap", "karein",
                 "kya", "nahi", "hai", "hain", "chahiye", "band", "khata"}
    words = set(re.sub(r'[^\w\s]', '', text.lower()).split())
    if words & romanized:
        return "ur"

    return "en"
