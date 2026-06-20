# DECISIONS.md

Every meaningful design choice, the alternatives considered, and why I chose.

---

## 1. Architecture: LLM at the edges, not in the middle

**Decision:** The LLM is used exactly once per request — to write the final natural-language reply. Every other step is pure deterministic code: language detection, KB retrieval, routing, and all safety decisions.

**Alternatives considered:**
- LLM-as-judge: pass question + context to the LLM and ask it to decide. Simpler to write, but safety decisions become non-deterministic and untestable. A prompt change or model upgrade can silently break a compliance rule.
- RAG-first: embed the question, vector-search the KB, feed top-N chunks to the LLM and let it answer. Works well for large KBs but introduces retrieval uncertainty and makes it hard to assert "the bot will never share a CNIC."

**Why I chose this:** Tests verify the architecture, not the model. Every refusal and escalation has a named code path. A compliance audit can read `decision_engine.py` and see exactly what the bot will do — no inference required.

---

## 2. Two data sources with different access rules

**Decision:** The knowledge base and customer records serve different purposes and require different rules.

- **Policy questions** (how to freeze, tap-to-pay, refund timelines) require a KB match. If no match, the bot must not invent policy.
- **Account questions** (balance, card status, recent transactions) are answered directly from safe fields. No KB article is required for a customer to receive their own account data.
- **Restricted fields** (CNIC, PAN, IBAN) are never shared regardless of what is asked.

**Why this matters:** "What's my balance?" has no KB article. If I had required a KB article for every answer, the bot would refuse this question — which is wrong. The `safe/restricted` split in `customers.json` *is* the access control policy. KB articles govern procedures; safe fields govern data access. These are different things and must be treated differently.

**Alternative considered:** Treat all data questions as requiring KB coverage. Rejected: would make the bot useless for basic account enquiries, which is not the intent of the materials.

---

## 3. "What's my balance?" — answered from safe data, no KB article needed

**Decision:** Answer with the balance from safe fields.

**Why:** Balance is explicitly marked as `safe` in `customers.json`. The assignment states: *"RESTRICTED fields must NEVER appear in a reply."* It does not say safe fields require an approved article. Refusing this question because no article exists would be a design failure, not a safety win.

**Interview answer:** *"The data model already encodes the access policy. I trust it. The KB governs policy; safe fields govern data exposure. These are orthogonal."*

---

## 4. "Charged twice for Netflix" — escalate, not answer

**Decision:** Escalate. The bot states observable facts ("I can see two Netflix charges for the same amount on the same date, one flagged as a possible duplicate") but does not conclude the cause or initiate any action.

**Why:** The bot may state observations, never inferences. Two transactions are observable. A duplicate charge is an interpretation. No approved dispute or refund-investigation policy exists in the KB. Inventing one ("please wait 3–5 business days") would be hallucinating policy — the exact failure mode this exercise is testing for.

**Alternative considered:** Point the customer to the refund-timeline KB article. Rejected: refund timeline covers merchant-initiated refunds, not disputes. Applying it here would misrepresent what the policy actually covers.

---

## 5. "Why can't I do anything?" (cust_003) — report facts, escalate for resolution

**Decision:** Report the observable safe-field facts (account status: restricted, KYC: pending) and escalate to a human agent for resolution steps.

**Why:** The bot can see the account is restricted and KYC is pending. These are safe facts and the customer can receive them. However, the bot cannot infer *why* these states are related, and no approved policy explains how to resolve a restricted account with pending KYC. Inventing steps would be hallucinating policy. The correct response is: here is what I can observe; a human agent can take it from here.

**What the bot does NOT say:** "Your account was restricted because your KYC is pending." That is a causal inference the bot is not authorised to make.

---

## 6. "Can I use tap to pay?" (cust_002, card frozen) — enriched answer

**Decision:** Answer the tap-to-pay policy question AND include the card-frozen context.

**Rule:** When approved KB content exists AND relevant safe account context materially affects the answer, the formatter may enrich the response with that context.

**Why:** Answering only "tap to pay works with a physical card" while knowing the customer's card is frozen is technically correct but unhelpful. The safe data is available and directly relevant. This is personalisation within governance — the KB covers the policy, the safe field covers the state, and the formatter combines them.

**Alternative considered (Position A):** Answer only the KB policy, never mention account state unless asked. Rejected: treats the bot as a static FAQ rather than a context-aware assistant. The interplay between policy and account state is exactly where this bot adds value.

---

## 7. Restricted data — refused unconditionally, before anything else

**Decision:** The restricted-data check runs first, before KB retrieval and before any account-data logic. A restricted-data request can never reach the KB path or the formatter.

**Why:** Defense in depth. Even if a KB article accidentally mentioned PAN numbers, the restricted check would fire first and refuse. The check is also unconditional — the bot does not explain *which* field is restricted or *why* it cannot be shared, to avoid confirming the field exists.

**Fields treated as restricted:** CNIC, PAN / full card number, IBAN. These map directly to the `restricted` keys in `customers.json`. Restricted field *values* are never loaded into bot memory — only the key names are stored, solely to support the keyword check.

---

## 8. Urdu question — respond professionally in the same language

**Decision:** Detect the question language (Urdu script or romanized Urdu) and instruct the formatter to respond in the same language. No humour, no irony — professional and warm throughout.

**Why:** Romanized Urdu (Urdu written in Latin script) is the dominant register for informal Pakistani digital communication. "Mera card freeze kaise karun?" is a legitimate customer message, not an edge case. The bot should respond in kind.

**What I ruled out:** Responding in English when the question was in Urdu (disrespectful, unhelpful). Adding humour about the card already being frozen (inappropriate for fintech support — the correct framing is "context-aware state enrichment", not irony).

**Note:** Hamza's card is already frozen when he asks how to freeze it. The correct response tells him the card is already frozen and explains how to *unfreeze* it. This is state-aware and helpful.

---

## 9. Three-way classification for unknown questions

There are three distinct cases when the bot has no KB match and no account data to return. They require different actions.

**Case 1 — PayWallet-related question, no approved answer** (e.g., savings interest rate, crypto, international transfers)
→ **ESCALATE.** This is a legitimate product question. The bot cannot answer it safely, but a human agent can. Returning `OUT_OF_SCOPE` would tell the customer "we can't help" — which is wrong.

**Case 2 — Account problem requiring investigation** (e.g., duplicate charge, restricted account)
→ **ESCALATE.** The bot observes facts but has no approved resolution path. A human must review.

**Case 3 — Truly unrelated question** (e.g., weather, sports, coding help)
→ **OUT_OF_SCOPE.** Not a PayWallet support request. A human agent cannot help either. No escalation needed.

**How Case 1 is detected:** A domain keyword list (`_PAYWALLET_DOMAIN_KEYWORDS`) covers financial and product terms — "interest", "rate", "crypto", "transfer", "loan", "savings", "card", etc. If any match, the question is PayWallet-related and escalates. If none match, it is truly out of scope.

**Alternative considered:** Use the LLM to classify domain relevance. Rejected: adds latency and non-determinism for a binary decision. A keyword list is sufficient, testable, and explainable to a compliance team.

**What the internal `question_type` field preserves:** Both Case 1 and Case 2 produce `action=ESCALATE` but `question_type=OUT_OF_SCOPE` vs `question_type=ACCOUNT` respectively. Downstream routing and analytics can use this to triage the queue differently — product questions to a product specialist, account problems to account operations.

---

## 10. Retrieval: keyword matching, not embeddings

**Decision:** The retriever uses weighted keyword matching. Multi-word phrases score proportionally to their word count (higher specificity = higher score). Title word bonus only applies when at least one keyword already matches.

**Why:** The KB has 6 sections. Embeddings add a non-deterministic dependency (embedding model drift, API availability) and would make retrieval behaviour hard to assert in tests. For a KB this size, keyword matching is more reliable and fully testable.

**The title-bonus guard:** Without requiring at least one keyword match before awarding title-word bonus, generic words like "account" in "Account deletion" would score unrelated questions (e.g., "savings account interest rate"). The guard prevents this false-positive retrieval.

---

## 11. Stub formatter in tests

**Decision:** All tests use `StubFormatter`, which returns templated strings encoding the action and reason. No LLM calls in the test suite.

**Why:** The tests verify decision logic, not response quality. Using a real LLM in tests would make them slow, expensive, non-deterministic, and dependent on API availability. The stub lets every test assertion be on a code path, not a language model output.

**What this means:** A test that says `assert response.action == Action.REFUSE` is asserting that the *architecture* refused the request. Whether the final words are polite is a separate concern, validated manually by running `python run_questions.py`.

---

## 12. Visible problem detection is question-aware

**Decision:** The duplicate-transaction escalation only fires when the question is actually about transactions or charges. A card-status question from a customer who also has a flagged transaction does not escalate.

**The problem it solves:** Hamza has both a frozen card and a possible duplicate Netflix charge. Under the original logic, any account data question from Hamza would escalate because `_detect_visible_problem` was customer-level, not question-level. So "what am I not able to pay?" escalated — even though the answer ("your card is frozen") was right there in safe data and had nothing to do with the duplicate charge.

**How it works:** `_detect_visible_problem` now takes the question as a second argument. The duplicate-transaction check only fires if the question contains transaction keywords (`charged`, `twice`, `netflix`, `duplicate`, etc.). The account-restriction check still fires unconditionally — a restricted account affects every interaction.

**Alternative considered:** Always escalate if any visible problem exists. Rejected: problems don't bleed into each other. A frozen card question and a duplicate charge question are separate issues. Escalating the former because of the latter conflates two unrelated concerns and gives the customer a worse experience.

---

## 13. Safe account context passed to all decisions including REFUSE

**Decision:** Every Decision object — including REFUSE and PayWallet ESCALATE — carries the full safe account context. Previously REFUSE passed nothing to the formatter.

**Why:** The LLM formatter always knows who it is talking to. Even for a refusal, having the customer's account state lets the LLM write a more grounded, personalised response ("Hi Ayesha, I'm not able to share that information" with confidence, or adding relevant context if appropriate).

**The safety boundary that does not change:** `account_context` is always built from `customer.safe.to_dict()` — the safe fields only. Restricted field values (`cnic`, `pan`, `iban`) are never loaded into memory at all, so they cannot appear in `account_context` regardless of which code path fires.

**What this means for REFUSE specifically:** The LLM receives the customer's safe data but is instructed not to volunteer information. For a refusal, it will not randomly mention the balance — but it has the context available if it naturally supports the response.

---

## 14. Problem message derived from actual transaction data, not a static string

**Decision:** The duplicate-transaction problem description is built from the flagged transaction record itself, not a hardcoded string.

**Before:** `"two transactions with the same amount and merchant on the same date (one is flagged as a possible duplicate)"` — always the same words regardless of which merchant or amount was involved.

**After:** `f"transaction flagged as possible duplicate: '{flagged[0]}'"` — includes the actual transaction text (`"PKR 250 to Netflix · 12 Jun · sent (duplicate?)"`) so the human agent receiving the escalation sees the real data.

**Why it matters:** The previous version was a static description that happened to match the mock data. If the flagged transaction were a Daraz charge for PKR 1,200, the message would still say "Netflix" in spirit. The fix makes the message data-driven — it reports exactly what it observes.

---

## 15. Structured logging across all pipeline stages

**Decision:** Every request is logged with a unique 8-character request ID, tracing all four stages: customer loaded, KB matched, decision made, LLM prompt sent, LLM response received. Logs go to both console and a rotating file (`logs/bot.log`, 1 MB × 5 files).

**What is logged at each stage:**
- `REQUEST` — customer ID and question
- `CUSTOMER` — safe account fields (status, card, balance, KYC)
- `KB_MATCH` — which KB sections matched (or none)
- `DECISION` — action, question type, language, reason
- `ACCT_DATA` — full safe context passed to formatter
- `LLM_SYSTEM` / `LLM_PROMPT` — exact text sent to the LLM
- `LLM_REPLY` — LLM response and latency in seconds

**What is never logged:** Restricted field values (`cnic`, `pan`, `iban`) — these are never loaded into memory at any stage, so they cannot appear in logs regardless of what is asked.

**Why the request ID matters:** A single customer question fans out across four components. Without a shared ID, correlating the KB match with the LLM prompt for the same request is impossible in a multi-request log file. The ID ties every line for one request together.

**Alternative considered:** Log only errors. Rejected: the LLM prompt is the most important thing to inspect when the bot gives a wrong answer. Silent-success logging would make debugging slow and post-mortems unreliable.

---

## 16. What I'm unsure about

**Urdu language detection.** The romanized Urdu detector uses a static word list (`mera`, `kaise`, `karun`, etc.). I'm not confident this handles all dialects, regional variations, or heavily mixed-language sentences. A customer writing `"mujhe apna balance batao"` would be missed because `mujhe` and `batao` aren't in the list. In production I would use a proper language-detection library (e.g. `langdetect` or `fastText`) rather than a word list. For the exercise I kept it simple and deterministic so it's fully testable — but I'm aware it's incomplete coverage.

---

## 17. What I deliberately left out

- **Confidence scoring / threshold:** The KB is small and hand-curated. A numerical confidence threshold adds complexity without value at this scale.
- **Caching:** Not relevant for a demo with 9 questions.
- **Authentication / session management:** Out of scope for this exercise.
- **Vector embeddings:** Overkill for 6 KB sections. If the KB grew to hundreds of articles, I would add them.
