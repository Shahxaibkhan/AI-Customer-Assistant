"""
Web chat UI for the PayWallet support bot.

Usage:
    python web_chat.py              # real LLM (requires GROQ_API_KEY in .env)
    python web_chat.py --stub       # stub formatter, no API key needed

Then open: http://localhost:5000
"""
import os
import sys
import json

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify

from src.loader import load_customers, load_knowledge
from src.bot import SupportBot
from src.formatter import StubFormatter, GroqFormatter

app = Flask(__name__)

customers = load_customers("materials/customers.json")
knowledge = load_knowledge("materials/knowledge.md")

if "--stub" in sys.argv:
    formatter = StubFormatter()
    mode_label = "Stub Mode"
elif os.environ.get("GROQ_API_KEY"):
    formatter = GroqFormatter()
    mode_label = "LLM Mode (Groq / Llama)"
else:
    formatter = StubFormatter()
    mode_label = "Stub Mode (no API key found)"

use_stub = isinstance(formatter, StubFormatter)
bot = SupportBot(customers=customers, knowledge_sections=knowledge, formatter=formatter)

CUSTOMER_LIST = json.dumps([
    {
        "id": cid,
        "name": c.safe.first_name,
        "status": c.safe.account_status,
        "card": c.safe.card_status,
        "kyc": c.safe.kyc,
        "balance": c.safe.balance,
        "transactions": c.safe.recent_transactions,
    }
    for cid, c in customers.items()
])


@app.route("/")
def index():
    html = _HTML.replace("__CUSTOMERS__", CUSTOMER_LIST)
    html = html.replace("__MODE__", mode_label)
    html = html.replace("__IS_STUB__", "true" if use_stub else "false")
    return html


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    customer_id = data.get("customer_id", "")
    message = data.get("message", "").strip()

    if not message or customer_id not in customers:
        return jsonify({"error": "invalid request"}), 400

    response = bot.answer(customer_id, message)
    action = str(response.action).split(".")[-1].lower()

    return jsonify({
        "action": action,
        "text": response.text,
        "reason": response.decision.reason if response.decision else "",
        "language": response.decision.language if response.decision else "en",
    })


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PayWallet Support Bot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;height:100vh;display:flex;background:#f1f5f9;overflow:hidden}

/* ── Sidebar ── */
.sidebar{width:272px;background:#0f172a;display:flex;flex-direction:column;flex-shrink:0}
.sidebar-header{padding:20px;border-bottom:1px solid #1e293b}
.sidebar-header h1{font-size:17px;font-weight:700;color:#f8fafc;letter-spacing:-.3px}
.sidebar-header p{font-size:12px;color:#475569;margin-top:3px}
.mode-pill{display:inline-block;margin-top:10px;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}
.mode-llm{background:#14532d;color:#86efac}
.mode-stub{background:#1e3a5f;color:#93c5fd}

.section-label{padding:16px 16px 6px;font-size:10px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:.08em}

.acct-card{margin:3px 10px;padding:11px 12px;border-radius:8px;cursor:pointer;border:1.5px solid transparent;transition:all .15s}
.acct-card:hover{background:#1e293b}
.acct-card.active{background:#1e293b;border-color:#3b82f6}
.acct-name{font-size:14px;font-weight:600;color:#f1f5f9}
.acct-id{font-size:11px;color:#475569;margin-top:1px}
.acct-badges{display:flex;gap:5px;margin-top:7px;flex-wrap:wrap}
.bdg{padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600}
.bdg-active{background:#14532d;color:#86efac}
.bdg-restricted,.bdg-blocked{background:#7f1d1d;color:#fca5a5}
.bdg-frozen{background:#78350f;color:#fcd34d}
.bdg-pending{background:#3b1f6e;color:#c4b5fd}
.bdg-verified{background:#14532d;color:#86efac}
.bdg-card{background:#1e3a5f;color:#93c5fd}

/* ── Chat area ── */
.chat{flex:1;display:flex;flex-direction:column;min-width:0}
.chat-header{padding:14px 24px;background:white;border-bottom:1px solid #e2e8f0;flex-shrink:0}
.chat-header-name{font-size:15px;font-weight:600;color:#0f172a}
.chat-header-sub{font-size:12px;color:#64748b;margin-top:2px}

.messages{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:14px}
.messages::-webkit-scrollbar{width:4px}
.messages::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:2px}

.empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:#94a3b8;text-align:center}
.empty-icon{font-size:44px}
.empty p{font-size:14px}
.empty small{font-size:12px;color:#cbd5e1}

.msg-row{display:flex;gap:8px;align-items:flex-end}
.msg-row.user{flex-direction:row-reverse}
.avatar{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0}
.avatar.bot{background:#dbeafe;color:#1d4ed8}
.avatar.user{background:#3b82f6;color:white}

.bubble{max-width:68%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.55;word-break:break-word}
.bubble.user{background:#3b82f6;color:white;border-bottom-right-radius:3px}
.bubble.bot{background:white;color:#1e293b;border-bottom-left-radius:3px;box-shadow:0 1px 3px rgba(0,0,0,.07)}

.action-pill{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
.ap-answer{background:#dcfce7;color:#166534}
.ap-escalate{background:#ffedd5;color:#9a3412}
.ap-refuse{background:#fee2e2;color:#991b1b}
.ap-out_of_scope{background:#f1f5f9;color:#475569}

.reason{font-size:11px;color:#94a3b8;font-style:italic;border-top:1px solid #f8fafc;padding-top:6px;margin-top:6px;line-height:1.4}

.typing-dots span{display:inline-block;width:6px;height:6px;border-radius:50%;background:#94a3b8;margin:0 2px;animation:bounce .9s infinite}
.typing-dots span:nth-child(2){animation-delay:.15s}
.typing-dots span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}

/* ── Input ── */
.input-wrap{padding:14px 24px;background:white;border-top:1px solid #e2e8f0;display:flex;gap:10px;flex-shrink:0}
.msg-input{flex:1;padding:9px 14px;border:1.5px solid #e2e8f0;border-radius:8px;font-size:14px;outline:none;transition:border-color .15s;color:#0f172a}
.msg-input:focus{border-color:#3b82f6}
.msg-input:disabled{background:#f8fafc;color:#94a3b8}
.send-btn{padding:9px 20px;background:#3b82f6;color:white;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:background .15s;white-space:nowrap}
.send-btn:hover:not(:disabled){background:#2563eb}
.send-btn:disabled{background:#cbd5e1;cursor:not-allowed}
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-header">
    <h1>PayWallet Support</h1>
    <p>AI Customer Assistant</p>
    <span class="mode-pill __MODE_CLASS__">__MODE__</span>
  </div>
  <div class="section-label">Accounts</div>
  <div id="acct-list"></div>
</div>

<div class="chat">
  <div class="chat-header">
    <div class="chat-header-name" id="hdr-name">No account selected</div>
    <div class="chat-header-sub" id="hdr-sub">Choose an account from the sidebar to begin</div>
  </div>
  <div class="messages" id="messages">
    <div class="empty" id="empty-state">
      <div class="empty-icon">💬</div>
      <p>Select a customer account to start</p>
      <small>Try: "what's my balance?" or "how do I freeze my card?"</small>
    </div>
  </div>
  <div class="input-wrap">
    <input class="msg-input" id="msg-input" placeholder="Select an account first…" disabled />
    <button class="send-btn" id="send-btn" onclick="send()" disabled>Send</button>
  </div>
</div>

<script>
const CUSTOMERS = __CUSTOMERS__;
const IS_STUB = __IS_STUB__;
let current = null;

// fix mode pill class
document.querySelector('.mode-pill').classList.add(IS_STUB ? 'mode-stub' : 'mode-llm');
document.querySelector('.mode-pill').classList.remove('__MODE_CLASS__');

function bdgClass(type, val) {
  if (type === 'kyc') return val === 'verified' ? 'bdg-verified' : 'bdg-pending';
  const m = {active:'bdg-active',restricted:'bdg-restricted',blocked:'bdg-blocked',frozen:'bdg-frozen'};
  return m[val] || 'bdg-card';
}

const list = document.getElementById('acct-list');
CUSTOMERS.forEach(c => {
  const el = document.createElement('div');
  el.className = 'acct-card';
  el.id = 'ac-' + c.id;
  el.onclick = () => select(c);
  el.innerHTML =
    '<div class="acct-name">' + c.name + '</div>' +
    '<div class="acct-id">' + c.id + '</div>' +
    '<div class="acct-badges">' +
      '<span class="bdg ' + bdgClass('status', c.status) + '">' + c.status + '</span>' +
      '<span class="bdg ' + bdgClass('card', c.card) + '">card: ' + c.card + '</span>' +
      '<span class="bdg ' + bdgClass('kyc', c.kyc) + '">kyc: ' + c.kyc + '</span>' +
    '</div>';
  list.appendChild(el);
});

function select(c) {
  current = c;
  document.querySelectorAll('.acct-card').forEach(e => e.classList.remove('active'));
  document.getElementById('ac-' + c.id).classList.add('active');
  document.getElementById('hdr-name').textContent = c.name + ' — ' + c.id;
  document.getElementById('hdr-sub').textContent =
    'Balance: ' + c.balance + '  ·  Account: ' + c.status + '  ·  Card: ' + c.card + '  ·  KYC: ' + c.kyc;
  const msgs = document.getElementById('messages');
  msgs.innerHTML = '';
  const input = document.getElementById('msg-input');
  input.disabled = false;
  input.placeholder = 'Ask ' + c.name + ' a question…';
  document.getElementById('send-btn').disabled = false;
  input.focus();
}

function appendMsg(role, text, action, reason) {
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'msg-row ' + role;

  const av = document.createElement('div');
  av.className = 'avatar ' + role;
  av.textContent = role === 'user' ? (current ? current.name[0] : 'U') : 'PW';

  const bub = document.createElement('div');
  bub.className = 'bubble ' + role;

  if (role === 'bot' && action) {
    const pill = document.createElement('div');
    pill.className = 'action-pill ap-' + action;
    pill.textContent = action.replace('_', ' ');

    const txt = document.createElement('div');
    txt.textContent = text;

    bub.appendChild(pill);
    bub.appendChild(txt);

    if (reason) {
      const r = document.createElement('div');
      r.className = 'reason';
      r.textContent = reason;
      bub.appendChild(r);
    }
  } else {
    bub.textContent = text;
  }

  row.appendChild(av);
  row.appendChild(bub);
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
}

function showTyping() {
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'msg-row bot'; row.id = 'typing';
  row.innerHTML = '<div class="avatar bot">PW</div><div class="bubble bot"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
  msgs.appendChild(row);
  msgs.scrollTop = msgs.scrollHeight;
}
function hideTyping() { const el = document.getElementById('typing'); if (el) el.remove(); }

async function send() {
  if (!current) return;
  const input = document.getElementById('msg-input');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.disabled = true;
  document.getElementById('send-btn').disabled = true;

  appendMsg('user', msg);
  showTyping();

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer_id: current.id, message: msg})
    });
    const d = await res.json();
    hideTyping();
    appendMsg('bot', d.text, d.action, d.reason);
  } catch(e) {
    hideTyping();
    appendMsg('bot', 'Could not reach the server.', 'escalate', '');
  }

  input.disabled = false;
  document.getElementById('send-btn').disabled = false;
  input.focus();
}

document.getElementById('msg-input').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"\nPayWallet Support Bot — {mode_label}")
    print("Open: http://localhost:5000\n")
    app.run(debug=False, port=5000)
