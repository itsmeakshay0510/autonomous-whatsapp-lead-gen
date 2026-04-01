"""
PHN Technology - FAQ Tool
Searches FAQs using keyword + tag matching.
"""

import json
import os
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "faqs.json")


class FAQTool:
    """Search FAQs by keyword and tag matching."""

    def __init__(self):
        self._faqs = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._faqs = data.get("faqs", [])
        self._loaded = True
        logger.info(f"Loaded {len(self._faqs)} FAQs")

    def search(self, query: str, max_results: int = 2) -> str:
        """
        Search FAQs matching the query.
        Returns formatted answer string.
        """
        self._load()
        query_lower = query.lower().strip()
        results = []

        for faq in self._faqs:
            score = 0

            # Check tags (highest priority)
            for tag in faq.get("tags", []):
                if tag in query_lower:
                    score += 5
                elif any(
                    SequenceMatcher(None, word, tag).ratio() > 0.7
                    for word in query_lower.split()
                    if len(word) >= 3
                ):
                    score += 3

            # Check question text
            q_lower = faq["question"].lower()
            for word in query_lower.split():
                if len(word) >= 3 and word in q_lower:
                    score += 2

            # Check category
            if faq.get("category", "").lower() in query_lower:
                score += 3

            if score > 0:
                results.append((score, faq))

        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:max_results]

        if not results:
            return ""  # Empty means no FAQ found; agent should use its own knowledge

        answers = []
        for _, faq in results:
            answers.append(faq["answer"])

        return "\n\n".join(answers)


# Singleton
_tool = FAQTool()


def get_faq_answer(query: str) -> str:
    """Get FAQ answer — callable function for the agent."""
    return _tool.search(query)
