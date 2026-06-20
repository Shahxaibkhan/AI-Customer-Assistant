import os
import time
from abc import ABC, abstractmethod
from .models import Action, Decision
from .logger import get_logger

log = get_logger()


class FormatterBase(ABC):
    @abstractmethod
    def format(self, decision: Decision, req_id: str = "-") -> str:
        ...


class StubFormatter(FormatterBase):
    """
    Deterministic formatter used in tests. Returns structured strings
    that encode the decision action and key context so test assertions
    can verify bot behaviour without any LLM call.
    """

    _TEMPLATES = {
        Action.ANSWER:       "[ANSWER] {name}: {reason}",
        Action.REFUSE:       "[REFUSE] {name}: I'm not able to share that information.",
        Action.ESCALATE:     "[ESCALATE] {name}: {reason}",
        Action.OUT_OF_SCOPE: "[OUT_OF_SCOPE] {name}: That's not something I can help with through this channel.",
    }

    def format(self, decision: Decision, req_id: str = "-") -> str:
        template = self._TEMPLATES[decision.action]
        return template.format(
            name=decision.customer_first_name,
            reason=decision.reason,
        )


_SYSTEM_PROMPT = """You are a professional customer support assistant for PayWallet, a Pakistani fintech app.

Rules you must follow without exception:
1. Be warm, professional, and concise — 2 to 4 sentences maximum.
2. Respond in the same language as the customer's question. If the question is in Urdu or romanized Urdu, reply in romanized Urdu (Latin script). Never switch languages mid-reply.
3. Use ONLY the information provided in the context. Never invent policies, fees, timelines, or steps.
4. If action is "refuse": politely decline. Do not explain which field is restricted or why it is restricted.
5. If action is "escalate": acknowledge what is observable, then offer to connect with a human agent. Never infer causes — only state observable facts.
6. If action is "out_of_scope": politely say this isn't something you can help with and suggest contacting support directly.
7. If action is "answer": answer using the provided knowledge and account context. If the customer's card is frozen and the question involves card usage, mention it.
8. Address the customer by their first name.
9. Never mention internal field names (cardStatus, kyc, pan, etc.)."""


def _build_prompt(decision: Decision) -> str:
    chunks = "\n\n".join(
        f"### {s.title}\n{s.content}" for s in decision.knowledge_chunks
    ) if decision.knowledge_chunks else "None"

    account = "\n".join(
        f"{k}: {v}" for k, v in decision.account_context.items()
    ) if decision.account_context else "None"

    return (
        f"Action: {decision.action}\n"
        f"Customer first name: {decision.customer_first_name}\n"
        f"Question language: {decision.language}\n"
        f"Original question: {decision.original_question}\n\n"
        f"Reason / decision context:\n{decision.reason}\n\n"
        f"Approved knowledge:\n{chunks}\n\n"
        f"Safe account context:\n{account}\n\n"
        "Write the customer reply now."
    )


class GroqFormatter(FormatterBase):
    """
    Groq formatter — uses Llama via Groq's API.
    Groq is OpenAI-compatible so uses the same chat completions format.
    """

    def __init__(self):
        try:
            import httpx
            from groq import Groq
            ssl_verify = os.environ.get("SSL_VERIFY", "true").lower() != "false"
            self._client = Groq(
                api_key=os.environ["GROQ_API_KEY"],
                http_client=httpx.Client(verify=ssl_verify),
            )
        except ImportError:
            raise RuntimeError("groq package not installed. Run: pip install groq")
        except KeyError:
            raise RuntimeError("GROQ_API_KEY environment variable not set.")

    def format(self, decision: Decision, req_id: str = "-") -> str:
        prompt = _build_prompt(decision)
        log.debug(f"[{req_id}] LLM_SYSTEM\n{_SYSTEM_PROMPT}")
        log.debug(f"[{req_id}] LLM_PROMPT\n{prompt}")

        t0 = time.time()
        response = self._client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=256,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )
        elapsed = time.time() - t0
        reply = response.choices[0].message.content.strip()

        log.info(f"[{req_id}] LLM_REPLY  ({elapsed:.2f}s)  {reply!r}")
        return reply
