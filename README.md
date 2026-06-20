# PayWallet Support Bot

A grounded customer-support AI that answers questions using approved help-center content and safe account data — with a deterministic decision engine that governs every safety-relevant choice.

## Quick start

```bash
pip install -r requirements.txt
```

**No API key? Everything still works.** Tests, the web UI, and the CLI all run in stub mode without any key.

### Stub mode vs LLM mode — what's the difference?

| | Stub mode | LLM mode |
|---|---|---|
| API key needed | No | Yes (Groq) |
| Response text | `[ANSWER] Ayesha: Account data question answered from safe customer fields.` | `Hi Ayesha, your current balance is PKR 3,420.10.` |
| What it proves | The routing decision is correct (ANSWER / REFUSE / ESCALATE) | The full end-to-end experience with natural language |
| Used in | Tests, code review, architecture demos | Live demo, user-facing |

Stub mode is intentional — tests verify the *decision*, not the words. The `[ANSWER]` prefix makes the action immediately visible.

---

### Run tests (no API key needed)

```bash
pytest tests/ -v
```

19 tests, all stubs, runs in under a second.

### Run the web UI — stub mode (no API key needed)

```bash
python web_chat.py --stub
```

Open `http://localhost:5000`. The sidebar shows **Stub Mode**. Responses look like:
```
[ANSWER] Ayesha: Account data question answered from safe customer fields.
```
This is correct — it shows the decision action and reason, not natural language.

### Run the web UI — LLM mode (Groq key needed)

Create a `.env` file in the project root:

```
GROQ_API_KEY=your-key-here
SSL_VERIFY=false     # only needed on corporate networks with SSL inspection (Zscaler etc.)
```

Then:

```bash
python web_chat.py
```

Open `http://localhost:5000`. The sidebar shows **LLM Mode (Groq / Llama)**. Responses are natural language:
```
Hi Ayesha, your current balance is PKR 3,420.10.
```

If no `.env` exists and no key is set, the bot silently falls back to stub mode — it never crashes on a missing key.

### Run all test questions in the terminal

```bash
python run_questions.py --stub     # no API key needed
python run_questions.py            # real LLM (needs key in .env)
```

## Project structure

```
support-bot/
├── materials/
│   ├── knowledge.md       # Approved help-center content (the only policy the bot may state)
│   ├── customers.json     # Mock account data — safe vs restricted split
│   └── questions.txt      # Test questions including edge cases
├── src/
│   ├── models.py          # Data types: Action, Decision, Customer, KnowledgeSection
│   ├── loader.py          # Parse customers.json and knowledge.md
│   ├── retriever.py       # Keyword-based KB retrieval
│   ├── decision_engine.py # All safety logic — pure code, no LLM
│   ├── formatter.py       # StubFormatter (tests) + GroqFormatter (production)
│   └── bot.py             # Orchestrates the four-stage pipeline
├── tests/
│   ├── conftest.py
│   ├── test_decision_engine.py   # Core behaviour tests
│   └── test_retriever.py         # Retrieval correctness tests
├── web_chat.py            # Flask web UI
├── run_questions.py       # CLI batch runner
├── DECISIONS.md           # Every meaningful design choice, justified
└── DESIGN.md              # Part 2 — scalable governed data layer
```

## Architecture

```
Customer ID + Question
        │
        ▼
  1. Load customer      ← pure code — restricted values never loaded into memory
        │
        ▼
  2. Retrieve KB        ← keyword matching, deterministic, no LLM
        │
        ▼
  3. Decision engine    ← pure code, outputs structured Decision
        │               (action: answer / refuse / escalate / out_of_scope)
        ▼
  4. Format response    ← LLM (production) or stub (tests)
        │
        ▼
     Reply
```

The LLM only touches language — understanding the question and phrasing the reply. Every safety decision is a deterministic code path with a test.

## Two data sources, different rules

| Source | Rule |
|--------|------|
| Knowledge base | Policy questions require a KB match. No match → bot must not invent policy. |
| Customer safe fields | Account questions answered directly. No KB article required. |
| Customer restricted fields | Never shared under any circumstances, even if explicitly asked. |

See `DECISIONS.md` for the full reasoning behind every design choice.
