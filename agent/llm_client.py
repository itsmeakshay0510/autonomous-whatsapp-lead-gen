"""
PHN Technology - Ollama LLM Client
Async wrapper for Ollama with optimized inference parameters.
"""

import logging
import time
from typing import Optional
from ollama import AsyncClient
from config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Async Ollama LLM client optimized for fast inference."""

    _instance: Optional["LLMClient"] = None

    def __init__(self):
        self.settings = get_settings()
        self._client = AsyncClient(host=self.settings.ollama_base_url)
        self._model = self.settings.ollama_model
        self._warmed_up = False

    @classmethod
    def get_instance(cls) -> "LLMClient":
        if cls._instance is None:
            cls._instance = LLMClient()
        return cls._instance

    async def warmup(self):
        """Pre-load model into memory for instant first response."""
        if self._warmed_up:
            return

        logger.info(f"Warming up model: {self._model}")
        start = time.time()
        try:
            # Send a minimal request to load the model
            await self._client.chat(
                model=self._model,
                messages=[{"role": "user", "content": "hi"}],
                options={
                    "num_predict": 1,
                    "num_ctx": self.settings.ollama_num_ctx,
                },
                keep_alive=-1,
            )
            elapsed = time.time() - start
            self._warmed_up = True
            logger.info(f"Model warmed up in {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"Model warmup failed: {e}")
            logger.error("Make sure Ollama is running and the model is pulled.")
            raise

    async def generate(self, messages: list[dict], temperature: float = None) -> str:
        """
        Generate a response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature

        Returns:
            Generated text response
        """
        start = time.time()

        try:
            response = await self._client.chat(
                model=self._model,
                messages=messages,
                options={
                    "num_predict": self.settings.ollama_num_predict,
                    "num_ctx": self.settings.ollama_num_ctx,
                    "temperature": temperature or self.settings.ollama_temperature,
                },
                keep_alive=self.settings.ollama_keep_alive,
            )

            elapsed = time.time() - start
            content = response["message"]["content"]

            # Log performance metrics
            eval_count = response.get("eval_count", 0)
            eval_duration = response.get("eval_duration", 0)
            if eval_duration > 0:
                tokens_per_sec = eval_count / (eval_duration / 1e9)
                logger.info(
                    f"LLM response: {eval_count} tokens in {elapsed:.2f}s "
                    f"({tokens_per_sec:.1f} tok/s)"
                )
            else:
                logger.info(f"LLM response in {elapsed:.2f}s")

            return content.strip()

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment."

    async def generate_with_tools(
        self,
        messages: list[dict],
        tool_definitions: list[dict],
        temperature: float = None
    ) -> dict:
        """
        Generate a response with tool-calling capability.

        Returns dict with 'content' and optionally 'tool_calls'.
        """
        start = time.time()

        try:
            response = await self._client.chat(
                model=self._model,
                messages=messages,
                tools=tool_definitions,
                options={
                    "num_predict": self.settings.ollama_num_predict,
                    "num_ctx": self.settings.ollama_num_ctx,
                    "temperature": temperature or self.settings.ollama_temperature,
                },
                keep_alive=self.settings.ollama_keep_alive,
            )

            elapsed = time.time() - start
            msg = response["message"]

            logger.info(f"LLM tool response in {elapsed:.2f}s")

            return {
                "content": msg.get("content", ""),
                "tool_calls": msg.get("tool_calls", []),
            }

        except Exception as e:
            logger.error(f"LLM tool generation failed: {e}")
            return {
                "content": "I'm sorry, I'm having trouble right now. Please try again.",
                "tool_calls": [],
            }

    async def check_health(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            models = await self._client.list()
            model_names = [m.get("name", "") for m in models.get("models", [])]
            have_model = any(self._model in name for name in model_names)
            if not have_model:
                logger.warning(
                    f"Model {self._model} not found. Available: {model_names}"
                )
            return have_model
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
