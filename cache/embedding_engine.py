"""
PHN Technology - Embedding Engine
Lightweight sentence embeddings for semantic caching.
Uses all-MiniLM-L6-v2 (~80MB) on CPU to keep GPU free for LLM.
"""

import numpy as np
from sentence_transformers import SentenceTransformer
import logging
import asyncio
from functools import lru_cache

logger = logging.getLogger(__name__)

# Model name - small, fast, good for similarity
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class EmbeddingEngine:
    """Generates text embeddings for semantic similarity matching."""

    _instance = None

    def __init__(self):
        self._model = None
        self._ready = False

    @classmethod
    def get_instance(cls) -> "EmbeddingEngine":
        if cls._instance is None:
            cls._instance = EmbeddingEngine()
        return cls._instance

    def load(self):
        """Load the embedding model (call at startup)."""
        if not self._ready:
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            self._model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            self._ready = True
            logger.info("Embedding model loaded successfully")

    def encode(self, text: str) -> np.ndarray:
        """Encode a single text string into an embedding vector."""
        if not self._ready:
            self.load()
        return self._model.encode(text, normalize_embeddings=True)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Encode multiple texts at once (more efficient)."""
        if not self._ready:
            self.load()
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32)

    async def async_encode(self, text: str) -> np.ndarray:
        """Async wrapper for encoding (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.encode, text)

    @staticmethod
    def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Compute cosine similarity between two normalized vectors."""
        return float(np.dot(vec_a, vec_b))

    @staticmethod
    def to_bytes(embedding: np.ndarray) -> bytes:
        """Convert numpy array to bytes for SQLite storage."""
        return embedding.astype(np.float32).tobytes()

    @staticmethod
    def from_bytes(data: bytes) -> np.ndarray:
        """Convert bytes back to numpy array."""
        return np.frombuffer(data, dtype=np.float32)
