import re
from .models import KnowledgeSection


class Retriever:
    """
    Keyword-based retriever over the knowledge base.

    Decision: for a KB with 6 sections, keyword matching is sufficient and
    fully deterministic — no embeddings needed. This makes retrieval testable
    and behaviour reproducible without an API call.
    """

    def __init__(self, sections: list):
        self._sections = sections

    def retrieve(self, question: str) -> list:
        q = self._normalize(question)
        scored = []

        for section in self._sections:
            score = self._score(q, section)
            if score > 0:
                scored.append((score, section))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored]

    def _score(self, normalized_question: str, section: KnowledgeSection) -> int:
        # Weight multi-word keywords higher than single words (more specific = more signal)
        kw_score = 0
        for kw in section.keywords:
            if kw in normalized_question:
                kw_score += len(kw.split())

        # Title bonus only applies when keyword evidence already exists.
        # Without this guard, generic words like "account" in "Account deletion"
        # would score unrelated questions (e.g. "savings account interest rate").
        if kw_score == 0:
            return 0

        title_score = 0
        for word in self._normalize(section.title).split():
            if len(word) > 3 and word in normalized_question:
                title_score += 1

        return kw_score + title_score

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'[^\w\s]', ' ', text.lower())
