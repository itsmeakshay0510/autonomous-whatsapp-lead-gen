"""
PHN Technology - Course Search Tool
Searches the course catalog with keyword and fuzzy matching.
"""

import json
import os
import logging
from typing import Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "courses.json")


class CourseSearchTool:
    """Search courses by keyword, category, or technology."""

    def __init__(self):
        self._courses = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._courses = data.get("courses", [])
        self._org_name = data.get("organization", "PHN Technology")
        self._loaded = True
        logger.info(f"Loaded {len(self._courses)} courses")

    def _fuzzy_match(self, query: str, text: str, threshold: float = 0.5) -> bool:
        """Check if query fuzzy-matches the text."""
        query_lower = query.lower()
        text_lower = text.lower()

        # Direct substring match
        if query_lower in text_lower:
            return True

        # Fuzzy word-level match
        query_words = query_lower.split()
        for word in query_words:
            if len(word) < 3:
                continue
            for text_word in text_lower.split():
                if SequenceMatcher(None, word, text_word).ratio() >= threshold:
                    return True
        return False

    def search(self, query: str, category: str = None, max_results: int = 3) -> str:
        """
        Search courses matching the query.
        Returns formatted string with course details.
        """
        self._load()
        query = query.strip()
        results = []

        for course in self._courses:
            score = 0

            # Category filter
            if category:
                if category.lower() in course["category"].lower():
                    score += 5
                else:
                    continue

            # Check name
            if self._fuzzy_match(query, course["name"]):
                score += 4

            # Check tags
            for tag in course.get("tags", []):
                if self._fuzzy_match(query, tag, 0.6):
                    score += 3
                    break

            # Check description
            if self._fuzzy_match(query, course["short_description"]):
                score += 2

            # Check modules
            for module in course.get("modules", []):
                if self._fuzzy_match(query, module, 0.6):
                    score += 2
                    break

            # Check category
            if self._fuzzy_match(query, course["category"]):
                score += 3

            if score > 0:
                results.append((score, course))

        # Sort by relevance score
        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:max_results]

        if not results:
            return "No courses found matching your query. We offer courses in AI/ML, Web Development, Data Science, Cybersecurity, and DevOps. Would you like to know about any of these?"

        return self._format_results(results)

    def get_all_courses_summary(self) -> str:
        """Get a brief summary of all courses."""
        self._load()
        lines = [f"📚 *{self._org_name} — Course Catalog*\n"]
        for i, course in enumerate(self._courses, 1):
            lines.append(
                f"{i}. *{course['name']}*\n"
                f"   ⏱ {course['duration']} | 💰 {course['fee']} | ⭐ {course['rating']}\n"
                f"   {course['short_description']}\n"
            )
        lines.append("Which course interests you? I'd love to share more details! 🎯")
        return "\n".join(lines)

    def get_course_detail(self, course_id: str) -> Optional[str]:
        """Get detailed info about a specific course."""
        self._load()
        for course in self._courses:
            if course["id"] == course_id:
                return self._format_detail(course)
        return None

    def _format_results(self, results: list) -> str:
        """Format search results for WhatsApp."""
        lines = []
        for _, course in results:
            lines.append(self._format_detail(course))
            lines.append("---")
        return "\n\n".join(lines)

    def _format_detail(self, course: dict) -> str:
        """Format a single course for WhatsApp."""
        modules_list = "\n".join(f"  • {m}" for m in course["modules"][:5])
        outcomes_list = "\n".join(f"  ✅ {o}" for o in course["key_outcomes"][:3])

        return (
            f"🎓 *{course['name']}*\n"
            f"📂 Category: {course['category']}\n"
            f"⏱ Duration: {course['duration']}\n"
            f"💰 Fee: {course['fee']}"
            f"{' (EMI: ' + course['emi_details'] + ')' if course['emi_available'] else ''}\n"
            f"🎯 Mode: {course['mode']}\n"
            f"⭐ Rating: {course['rating']} | 👥 {course['students_enrolled']}+ students enrolled\n"
            f"📅 Next Batch: {course['batch_starts']}\n"
            f"🪑 Seats Available: {course['seats_available']}\n\n"
            f"📝 {course['short_description']}\n\n"
            f"*Key Modules:*\n{modules_list}\n\n"
            f"*What You'll Achieve:*\n{outcomes_list}\n\n"
            f"*Prerequisites:* {course['prerequisites']}"
        )


# Singleton instance
_tool = CourseSearchTool()


def search_courses(query: str, category: str = None) -> str:
    """Search courses — callable function for the agent."""
    return _tool.search(query, category)


def get_all_courses() -> str:
    """Get summary of all courses."""
    return _tool.get_all_courses_summary()
