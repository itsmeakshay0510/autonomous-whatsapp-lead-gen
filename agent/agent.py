"""
PHN Technology - AI Agent Core
Orchestrates the full pipeline: Cache → Tools → LLM → Response.
"""

import logging
import time
import re
from typing import Optional

from agent.llm_client import LLMClient
from agent.prompt_builder import PromptBuilder
from cache.response_cache import ResponseCache
from memory.conversation_store import ConversationStore
from tools.search_courses import search_courses, get_all_courses
from tools.get_faq import get_faq_answer
from tools.save_student import save_student_info
from tools.set_reminder import set_reminder

logger = logging.getLogger(__name__)


# Tool definitions for Ollama tool-calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "Search for courses offered by PHN Technology. Use when the user asks about courses, programs, training, or mentions specific technologies like Python, AI, web development, data science, cybersecurity, devops.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query - what the user is looking for (e.g., 'machine learning', 'web development', 'python course')"
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter (e.g., 'AI & ML', 'Web Development', 'Data Science', 'Cybersecurity', 'DevOps & Automation')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_faq_answer",
            "description": "Get answers to frequently asked questions about PHN Technology - registration, fees, placement, timings, certificates, refunds, location, demo classes, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question to search for in FAQs"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_student_info",
            "description": "Save student registration information when they express interest in enrolling. Only use when the student provides their name, email, or explicitly wants to register.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Student's full name"
                    },
                    "email": {
                        "type": "string",
                        "description": "Student's email address"
                    },
                    "course": {
                        "type": "string",
                        "description": "Course the student is interested in"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a follow-up reminder for the student. Use when student wants to be reminded about batch dates, demo classes, or follow-ups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The reminder message content"
                    },
                    "hours_from_now": {
                        "type": "integer",
                        "description": "Number of hours from now to send the reminder (default: 24)"
                    }
                },
                "required": ["message"]
            }
        }
    }
]


class Agent:
    """
    Main AI Agent — orchestrates the full conversation pipeline.

    Pipeline:
    1. Check cache for instant response
    2. Load conversation history
    3. Determine and execute tools
    4. Generate LLM response with tool context
    5. Cache the response
    6. Save to conversation memory
    """

    def __init__(self):
        self.llm = LLMClient.get_instance()
        self.prompt_builder = PromptBuilder()
        self.cache = ResponseCache()
        self.memory = ConversationStore()

    async def initialize(self):
        """Initialize all components."""
        await self.cache.initialize()
        await self.llm.warmup()

    def _is_greeting(self, message: str) -> bool:
        """Check if message is a simple greeting."""
        greetings = {
            "hi", "hello", "hey", "hii", "hiii", "helo", "hellow",
            "good morning", "good afternoon", "good evening",
            "namaste", "namaskar", "howdy", "sup", "yo",
            "start", "menu", "help",
        }
        normalized = message.strip().lower().rstrip("!.,?")
        return normalized in greetings

    def _is_list_courses(self, message: str) -> bool:
        """Check if the user wants to see all courses."""
        patterns = [
            r"(all|list|show|what).*(course|program|offer)",
            r"course.*(list|catalog|available)",
            r"what.*(do you|you).*(offer|teach|provide)",
            r"what.*course",
        ]
        msg_lower = message.lower()
        return any(re.search(p, msg_lower) for p in patterns)

    async def _execute_tool(self, tool_name: str, args: dict, phone: str) -> str:
        """Execute a tool and return its result."""
        try:
            if tool_name == "search_courses":
                return search_courses(
                    query=args.get("query", ""),
                    category=args.get("category")
                )
            elif tool_name == "get_faq_answer":
                return get_faq_answer(query=args.get("query", ""))
            elif tool_name == "save_student_info":
                return await save_student_info(
                    phone=phone,
                    name=args.get("name"),
                    email=args.get("email"),
                    course=args.get("course")
                )
            elif tool_name == "set_reminder":
                return await set_reminder(
                    phone=phone,
                    message=args.get("message", "Follow up"),
                    hours_from_now=args.get("hours_from_now", 24)
                )
            else:
                logger.warning(f"Unknown tool: {tool_name}")
                return ""
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return f"Tool error: {str(e)}"

    async def process_message(self, phone: str, message: str) -> str:
        """
        Process an incoming message and return a response.
        This is the main entry point for the agent.
        """
        start_time = time.time()
        message = message.strip()

        # --- Step 0: Handle greetings instantly ---
        if self._is_greeting(message):
            greeting = self.prompt_builder.greeting
            await self.memory.add_turn(phone, "user", message)
            await self.memory.add_turn(phone, "assistant", greeting)
            elapsed = time.time() - start_time
            logger.info(f"Greeting response in {elapsed:.3f}s")
            return greeting

        # --- Step 0.5: Handle "show all courses" ---
        if self._is_list_courses(message):
            all_courses = get_all_courses()
            await self.memory.add_turn(phone, "user", message)
            await self.memory.add_turn(phone, "assistant", all_courses)
            elapsed = time.time() - start_time
            logger.info(f"All courses response in {elapsed:.3f}s")
            return all_courses

        # --- Step 1: Check cache ---
        cached_response, cache_type = await self.cache.lookup(message)
        if cached_response:
            await self.memory.add_turn(phone, "user", message)
            await self.memory.add_turn(phone, "assistant", cached_response)
            elapsed = time.time() - start_time
            logger.info(f"Cached ({cache_type}) response in {elapsed:.3f}s")
            return cached_response

        # --- Step 2: Load context ---
        conversation_history = await self.memory.get_history(phone)
        student_context = await self.memory.get_student_context(phone)

        # --- Step 3 & 4: LLM Generation and Tool Execution ---
        tool_results = {}

        # Build the full conversational prompt for the first LLM pass
        messages = self.prompt_builder.build_messages(
            user_message=message,
            conversation_history=conversation_history,
            tool_results=None,
            student_context=student_context,
        )

        # Let the LLM decide to answer naturally OR call tools
        llm_pass_1 = await self.llm.generate_with_tools(
            messages=messages,
            tool_definitions=TOOL_DEFINITIONS,
            temperature=0.7,
        )

        # Check if tools were invoked
        if llm_pass_1.get("tool_calls"):
            for tool_call in llm_pass_1["tool_calls"]:
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                tool_args = func.get("arguments", {})

                logger.info(f"Executing tool: {tool_name}({tool_args})")
                result = await self._execute_tool(tool_name, tool_args, phone)
                if result:
                    tool_results[tool_name] = result

            # Since tools were used, do a second LLM pass with the injected tool knowledge
            final_messages = self.prompt_builder.build_messages(
                user_message=message,
                conversation_history=conversation_history,
                tool_results=tool_results,
                student_context=student_context,
            )
            response = await self.llm.generate(final_messages)
        else:
            raw_content = llm_pass_1.get("content", "").strip()

            # Detect if llama3.1 put a tool call as raw text in content
            # e.g. {"name": "search_courses", "parameters": {...}}
            raw_tool_match = re.search(
                r'\{\s*["\']name["\']\s*:\s*["\']([\w]+)["\'].*?["\']parameters["\']\s*:\s*(\{.*?\})',
                raw_content, re.DOTALL
            )
            if raw_tool_match:
                tool_name = raw_tool_match.group(1)
                try:
                    import json
                    tool_args = json.loads(raw_tool_match.group(2))
                except Exception:
                    tool_args = {}
                logger.info(f"Detected raw text tool call: {tool_name}({tool_args})")
                result = await self._execute_tool(tool_name, tool_args, phone)
                if result:
                    tool_results[tool_name] = result
                final_messages = self.prompt_builder.build_messages(
                    user_message=message,
                    conversation_history=conversation_history,
                    tool_results=tool_results,
                    student_context=student_context,
                )
                response = await self.llm.generate(final_messages)
            else:
                response = raw_content
                # Failsafe
                if not response:
                    response = await self.llm.generate(messages)

        # --- Step 5: Post-processing ---
        # Clean up response (remove thinking tags, GuidId metadata, internal markers)
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        response = re.sub(r"GuidI?d[=:]?\s*[\w\-]+", "", response, flags=re.IGNORECASE)
        response = re.sub(r"\{\s*['\"]name['\"]\s*:\s*['\"]\w+['\"].*?\}", "", response, flags=re.DOTALL)
        response = response.strip()

        # Truncate if too long for WhatsApp (limit ~4000 chars)
        if len(response) > 3800:
            response = response[:3800] + "\n\n_...message truncated. Ask me to continue!_"

        # --- Step 6: Cache and save ---
        # Only cache if we got a meaningful response
        if len(response) > 20 and not tool_results.get("save_student_info"):
            await self.cache.store(message, response)

        await self.memory.add_turn(phone, "user", message)
        await self.memory.add_turn(phone, "assistant", response)

        elapsed = time.time() - start_time
        logger.info(f"Full agent response in {elapsed:.2f}s (tools: {list(tool_results.keys())})")

        return response
