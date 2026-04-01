"""
PHN Technology - Prompt Builder
Constructs optimized prompts with system instructions, history, and tool results.
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

PROMPTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "prompts.json")


class PromptBuilder:
    """Builds structured prompts for the LLM agent."""

    def __init__(self):
        self._prompts_data = None

    def _load_prompts(self):
        if self._prompts_data is None:
            with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
                self._prompts_data = json.load(f)

    @property
    def system_prompt(self) -> str:
        self._load_prompts()
        return self._prompts_data["system_prompt"]

    @property
    def greeting(self) -> str:
        self._load_prompts()
        return self._prompts_data["greeting_template"]

    @property
    def fallback(self) -> str:
        self._load_prompts()
        return self._prompts_data["fallback_template"]

    def registration_success(self, name: str, course: str) -> str:
        self._load_prompts()
        return self._prompts_data["registration_success_template"].format(
            name=name, course=course
        )

    def build_messages(
        self,
        user_message: str,
        conversation_history: list[dict] = None,
        tool_results: dict = None,
        student_context: dict = None,
    ) -> list[dict]:
        """
        Build the full message list for the LLM.

        Args:
            user_message: Current user message
            conversation_history: Past message list [{role, content}]
            tool_results: Dict of tool_name -> tool_output
            student_context: Known student info (name, email, course interest)

        Returns:
            List of messages formatted for Ollama chat API
        """
        messages = []

        # 1. System prompt with dynamic context
        system_content = self.system_prompt

        # Add student context if known
        if student_context:
            context_parts = []
            if student_context.get("name"):
                context_parts.append(f"Student Name: {student_context['name']}")
            if student_context.get("email"):
                context_parts.append(f"Email: {student_context['email']}")
            if student_context.get("interested_course"):
                context_parts.append(f"Interested In: {student_context['interested_course']}")
            if context_parts:
                system_content += (
                    f"\n\n## Known Student Information\n" +
                    "\n".join(f"- {p}" for p in context_parts)
                )

        # Add tool results if any
        if tool_results:
            tool_context = "\n\n## Information Retrieved (use this to answer the student)\n"
            for tool_name, result in tool_results.items():
                if result:
                    tool_context += f"\n### From {tool_name}:\n{result}\n"
            system_content += tool_context

        messages.append({"role": "system", "content": system_content})

        # 2. Conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # 3. Current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    def build_tool_selection_messages(
        self,
        user_message: str,
        conversation_history: list[dict] = None,
    ) -> list[dict]:
        """
        Build messages for the tool selection step.
        Returns messages that instruct the LLM to pick tools.
        """
        self._load_prompts()

        tool_instructions = self._prompts_data.get("tool_instructions", {})
        tool_guide = "\n".join(
            f"- **{name}**: {desc}" for name, desc in tool_instructions.items()
        )

        system_content = (
            "You are a tool-selection assistant. Based on the user's message, decide which tools to use.\n\n"
            f"Available tools:\n{tool_guide}\n\n"
            "If the user is greeting or having casual conversation, no tools are needed.\n"
            "If the user asks about courses, use search_courses.\n"
            "If the user asks a general question, use get_faq.\n"
            "If the user provides registration details, use save_student.\n"
        )

        messages = [{"role": "system", "content": system_content}]

        if conversation_history:
            # Only include last few turns for context
            messages.extend(conversation_history[-4:])

        messages.append({"role": "user", "content": user_message})

        return messages
