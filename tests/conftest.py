import re
import logging
from collections import defaultdict
from datetime import datetime

import pytest
from src.loader import load_customers, load_knowledge
from src.formatter import StubFormatter
from src.bot import SupportBot

MATERIALS = "materials"

# ── Shared fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def customers():
    return load_customers(f"{MATERIALS}/customers.json")


@pytest.fixture(scope="session")
def knowledge():
    return load_knowledge(f"{MATERIALS}/knowledge.md")


@pytest.fixture(scope="session")
def bot(customers, knowledge):
    return SupportBot(
        customers=customers,
        knowledge_sections=knowledge,
        formatter=StubFormatter(),
    )


# ── Report generation ────────────────────────────────────────────────────────

_test_results = []
_log_per_test = {}

_CATEGORIES = {
    "Security":     ["cnic", "iban", "card_number", "restricted_fields"],
    "Policy":       ["freeze_card", "tap_to_pay"],
    "Account Data": ["balance"],
    "Escalation":   ["duplicate", "restricted_account", "crypto", "savings", "out_of_scope"],
    "Language":     ["urdu", "english_question"],
    "Retriever":    [],
}

_CAT_ORDER = ["Security", "Policy", "Account Data", "Escalation", "Language", "Retriever"]


def _category(test_name):
    for cat, keywords in _CATEGORIES.items():
        if any(k in test_name for k in keywords):
            return cat
    return "Retriever"


def _readable(name):
    name = re.sub(r'^test_', '', name)
    return name.replace("_", " ").capitalize()


def _parse_decide(line):
    m = re.match(r"DECIDE\s+'(.+?)'\s+customer=(\w+)\s+→\s+(\w+)\s+reason=(.+)", line)
    if m:
        return {"question": m.group(1), "customer": m.group(2),
                "action": m.group(3), "reason": m.group(4)}
    return None


@pytest.fixture(autouse=True)
def _capture(request, caplog):
    with caplog.at_level(logging.INFO, logger="support_bot"):
        yield
    _log_per_test[request.node.nodeid] = [
        r.getMessage() for r in caplog.records if "DECIDE" in r.getMessage()
    ]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        raw_lines = _log_per_test.get(item.nodeid, [])
        decisions = [d for d in (_parse_decide(l) for l in raw_lines) if d]
        doc = (item.function.__doc__ or "").strip().splitlines()[0] if item.function.__doc__ else ""
        _test_results.append({
            "name": item.name,
            "readable": _readable(item.name),
            "category": _category(item.name),
            "status": rep.outcome,
            "duration_ms": round(rep.duration * 1000),
            "decisions": decisions,
            "doc": doc,
        })


def pytest_sessionfinish(session, exitstatus):
    if _test_results:
        _write_report(_test_results)


def _write_report(results):
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = len(results) - passed
    total_ms = sum(r["duration_ms"] for r in results)
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")

    ACTION_COLORS = {
        "ANSWER":       ("#14532d", "#86efac"),
        "REFUSE":       ("#7f1d1d", "#fca5a5"),
        "ESCALATE":     ("#78350f", "#fcd34d"),
        "OUT_OF_SCOPE": ("#1e293b", "#94a3b8"),
    }

    CAT_ICONS = {
        "Security":     "🔒",
        "Policy":       "📋",
        "Account Data": "💳",
        "Escalation":   "🔼",
        "Language":     "🌐",
        "Retriever":    "🔍",
    }

    def badge(action):
        bg, fg = ACTION_COLORS.get(action, ("#334155", "#94a3b8"))
        label = action.replace("_", " ")
        return (f'<span style="background:{bg};color:{fg};padding:2px 8px;'
                f'border-radius:4px;font-size:10px;font-weight:700;'
                f'letter-spacing:.05em;text-transform:uppercase">{label}</span>')

    def decision_card(d):
        b = badge(d["action"])
        q = d["question"][:80] + ("…" if len(d["question"]) > 80 else "")
        reason = d["reason"][:120] + ("…" if len(d["reason"]) > 120 else "")
        return f"""
        <div style="background:#0f172a;border-radius:6px;padding:8px 12px;margin-top:6px;
                    border-left:3px solid {'#22c55e' if d['action']=='ANSWER' else '#f97316' if d['action']=='ESCALATE' else '#ef4444' if d['action']=='REFUSE' else '#475569'}">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            {b}
            <span style="font-size:11px;color:#64748b">{d['customer']}</span>
          </div>
          <div style="font-size:12px;color:#e2e8f0;font-style:italic">"{q}"</div>
          <div style="font-size:11px;color:#475569;margin-top:3px">{reason}</div>
        </div>"""

    def test_row(r):
        dot_color = "#22c55e" if r["status"] == "passed" else "#ef4444"
        status_label = "PASS" if r["status"] == "passed" else "FAIL"
        status_bg = "#14532d" if r["status"] == "passed" else "#7f1d1d"
        status_fg = "#86efac" if r["status"] == "passed" else "#fca5a5"
        decisions_html = "".join(decision_card(d) for d in r["decisions"])
        doc_html = f'<div style="font-size:11px;color:#475569;margin-top:2px">{r["doc"]}</div>' if r["doc"] else ""
        return f"""
        <div style="background:#1e293b;border-radius:8px;padding:14px 16px;margin-bottom:6px">
          <div style="display:flex;align-items:flex-start;gap:12px">
            <div style="width:8px;height:8px;border-radius:50%;background:{dot_color};margin-top:5px;flex-shrink:0"></div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:8px">
                <span style="font-size:13px;font-weight:600;color:#f1f5f9">{r["readable"]}</span>
                <span style="background:{status_bg};color:{status_fg};padding:1px 7px;
                             border-radius:4px;font-size:10px;font-weight:700">{status_label}</span>
                <span style="font-size:11px;color:#334155;margin-left:auto">{r["duration_ms"]}ms</span>
              </div>
              {doc_html}
              {decisions_html}
            </div>
          </div>
        </div>"""

    sections_html = ""
    for cat in _CAT_ORDER:
        tests = by_cat.get(cat, [])
        if not tests:
            continue
        cat_pass = sum(1 for t in tests if t["status"] == "passed")
        icon = CAT_ICONS.get(cat, "")
        rows = "".join(test_row(t) for t in tests)
        sections_html += f"""
        <div style="margin:0 32px 28px">
          <div style="display:flex;align-items:center;gap:8px;padding:12px 0 8px;
                      border-bottom:1px solid #1e293b;margin-bottom:12px">
            <span style="font-size:16px">{icon}</span>
            <span style="font-size:12px;font-weight:700;text-transform:uppercase;
                         letter-spacing:.08em;color:#475569">{cat}</span>
            <span style="font-size:11px;color:#22c55e;margin-left:auto">{cat_pass}/{len(tests)} passed</span>
          </div>
          {rows}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PayWallet Bot — Test Report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0f172a;color:#f1f5f9;min-height:100vh}}
</style>
</head>
<body>

<div style="background:#1e293b;border-bottom:1px solid #334155;padding:24px 32px;
            display:flex;align-items:center;justify-content:space-between">
  <div>
    <div style="font-size:20px;font-weight:700;letter-spacing:-.3px">PayWallet Support Bot</div>
    <div style="font-size:13px;color:#475569;margin-top:3px">Decision Engine Test Report</div>
  </div>
  <div style="font-size:12px;color:#334155">{timestamp}</div>
</div>

<div style="display:flex;gap:16px;padding:24px 32px">
  <div style="flex:1;background:#1e293b;border-radius:12px;padding:20px">
    <div style="font-size:32px;font-weight:700;color:#f1f5f9">{len(results)}</div>
    <div style="font-size:12px;color:#475569;margin-top:4px;text-transform:uppercase;letter-spacing:.05em">Total Tests</div>
  </div>
  <div style="flex:1;background:#1e293b;border-radius:12px;padding:20px;border:1px solid #14532d">
    <div style="font-size:32px;font-weight:700;color:#22c55e">{passed}</div>
    <div style="font-size:12px;color:#475569;margin-top:4px;text-transform:uppercase;letter-spacing:.05em">Passed</div>
  </div>
  <div style="flex:1;background:#1e293b;border-radius:12px;padding:20px;{'border:1px solid #7f1d1d' if failed else ''}">
    <div style="font-size:32px;font-weight:700;color:{'#ef4444' if failed else '#334155'}">{failed}</div>
    <div style="font-size:12px;color:#475569;margin-top:4px;text-transform:uppercase;letter-spacing:.05em">Failed</div>
  </div>
  <div style="flex:1;background:#1e293b;border-radius:12px;padding:20px">
    <div style="font-size:32px;font-weight:700;color:#f1f5f9">{total_ms}ms</div>
    <div style="font-size:12px;color:#475569;margin-top:4px;text-transform:uppercase;letter-spacing:.05em">Duration</div>
  </div>
</div>

<div style="padding:0 0 32px">
  {sections_html}
</div>

</body>
</html>"""

    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
