import json
import re
from .models import Customer, SafeFields, KnowledgeSection


def load_customers(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    customers = {}
    for c in data["customers"]:
        safe_data = c["safe"]
        safe = SafeFields(
            first_name=safe_data["firstName"],
            account_status=safe_data["accountStatus"],
            balance=safe_data["balance"],
            card_status=safe_data["cardStatus"],
            kyc=safe_data["kyc"],
            recent_transactions=safe_data.get("recentTransactions", []),
        )
        # Store only restricted field names — values are never loaded into bot memory
        restricted_keys = list(c.get("restricted", {}).keys())
        customers[c["id"]] = Customer(
            id=c["id"],
            safe=safe,
            restricted_keys=restricted_keys,
        )

    return customers


def load_knowledge(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        content = f.read()

    sections = []
    # Split on ## headings
    parts = re.split(r'\n## ', content)

    for part in parts[1:]:  # skip preamble
        lines = part.strip().splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        section_id = re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')
        keywords = _keywords_for(title, body)

        sections.append(KnowledgeSection(
            id=section_id,
            title=title,
            content=body,
            keywords=keywords,
        ))

    return sections


def _keywords_for(title: str, body: str) -> list:
    """
    Keywords used by the retriever to match questions to sections.
    Defined explicitly per section rather than extracted — a small KB
    makes static definition more reliable than TF-IDF.
    """
    text = (title + " " + body).lower()

    keyword_groups = {
        "freeze": [
            "freeze", "frozen", "unfreeze", "band karo", "freeze kaise", "card band",
            # synonyms customers commonly use
            "suspend", "block card", "suspend card", "block my card", "suspend my card",
        ],
        "decline": ["declined", "decline", "rejected", "not working", "payment fail", "failing"],
        "refund": ["refund", "money back", "reversal", "refunded"],
        "otp": ["otp", "verification code", "sms code", "one time password"],
        "tap": ["tap to pay", "tap pay", "contactless", "nfc", "tap"],
        "delete": [
            "delete account", "close account", "remove account", "deletion",
            # "my" variants — phrase matching breaks without these
            "close my account", "delete my account", "remove my account",
        ],
    }

    matched = []
    for group_kws in keyword_groups.values():
        if any(kw in text for kw in group_kws):
            matched.extend(group_kws)

    return matched
