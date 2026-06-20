import uuid
from .models import BotResponse, Action
from .retriever import Retriever
from .decision_engine import DecisionEngine
from .formatter import FormatterBase
from .logger import get_logger

log = get_logger()


class SupportBot:
    """
    Orchestrates the four-stage pipeline:
      1. Load customer record (injected at construction)
      2. Retrieve relevant KB chunks (keyword match)
      3. Run decision engine (pure logic, no LLM)
      4. Format response (LLM in production, stub in tests)
    """

    def __init__(self, customers: dict, knowledge_sections: list, formatter: FormatterBase):
        self._customers = customers
        self._retriever = Retriever(knowledge_sections)
        self._engine = DecisionEngine()
        self._formatter = formatter

    def answer(self, customer_id: str, question: str) -> BotResponse:
        req_id = uuid.uuid4().hex[:8]

        # ── Stage 1: Customer lookup ─────────────────────────────────────
        log.info(f"[{req_id}] REQUEST    customer={customer_id!r}  question={question!r}")

        customer = self._customers.get(customer_id)
        if customer is None:
            log.warning(f"[{req_id}] NOT FOUND  customer_id={customer_id!r}")
            return BotResponse(
                action=Action.ESCALATE,
                text="I wasn't able to find your account. Please contact support.",
            )

        log.debug(f"[{req_id}] CUSTOMER   name={customer.safe.first_name!r}  "
                  f"status={customer.safe.account_status!r}  card={customer.safe.card_status!r}  "
                  f"kyc={customer.safe.kyc!r}  balance={customer.safe.balance!r}")

        # ── Stage 2: KB retrieval ────────────────────────────────────────
        chunks = self._retriever.retrieve(question)

        if chunks:
            log.info(f"[{req_id}] KB_MATCH   sections={[s.title for s in chunks]}")
        else:
            log.info(f"[{req_id}] KB_MATCH   sections=[]  (no match)")

        # ── Stage 3: Decision engine ─────────────────────────────────────
        decision = self._engine.decide(question, customer, chunks)

        log.info(f"[{req_id}] DECISION   action={str(decision.action).split('.')[-1].upper()}  "
                 f"type={str(decision.question_type).split('.')[-1]}  "
                 f"language={decision.language}")
        log.debug(f"[{req_id}] REASON     {decision.reason}")

        if decision.account_context:
            safe_keys = list(decision.account_context.keys())
            log.debug(f"[{req_id}] ACCT_CTX   keys={safe_keys}")
            log.debug(f"[{req_id}] ACCT_DATA  {decision.account_context}")

        if decision.knowledge_chunks:
            for chunk in decision.knowledge_chunks:
                log.debug(f"[{req_id}] KB_USED    [{chunk.title}]\n{chunk.content[:200]}...")

        # ── Stage 4: Format response ─────────────────────────────────────
        text = self._formatter.format(decision, req_id=req_id)

        log.info(f"[{req_id}] RESPONSE   {text!r}")
        log.info(f"[{req_id}] DONE")

        return BotResponse(action=decision.action, text=text, decision=decision)
