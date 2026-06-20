from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    ANSWER = "answer"
    REFUSE = "refuse"
    ESCALATE = "escalate"
    OUT_OF_SCOPE = "out_of_scope"


class QuestionType(str, Enum):
    RESTRICTED_DATA_REQUEST = "restricted_data_request"
    POLICY = "policy"
    ACCOUNT = "account"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class SafeFields:
    first_name: str
    account_status: str
    balance: str
    card_status: str
    kyc: str
    recent_transactions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "firstName": self.first_name,
            "accountStatus": self.account_status,
            "balance": self.balance,
            "cardStatus": self.card_status,
            "kyc": self.kyc,
            "recentTransactions": self.recent_transactions,
        }


@dataclass
class Customer:
    id: str
    safe: SafeFields
    restricted_keys: list = field(default_factory=list)


@dataclass
class KnowledgeSection:
    id: str
    title: str
    content: str
    keywords: list = field(default_factory=list)


@dataclass
class Decision:
    action: Action
    question_type: QuestionType
    reason: str
    knowledge_chunks: list = field(default_factory=list)
    account_context: dict = field(default_factory=dict)
    customer_first_name: str = ""
    language: str = "en"
    original_question: str = ""


@dataclass
class BotResponse:
    action: Action
    text: str
    decision: Optional[Decision] = None
