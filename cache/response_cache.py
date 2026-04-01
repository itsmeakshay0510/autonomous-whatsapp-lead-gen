"""
PHN Technology - Response Cache
3-layer caching: Exact Match → Semantic Match → LLM Fallback
Dramatically reduces response time for common queries.
"""

import hashlib
import numpy as np
import logging
import asyncio
from typing import Optional, Tuple

from database.db import Database
from cache.embedding_engine import EmbeddingEngine
from config import get_settings

logger = logging.getLogger(__name__)


class ResponseCache:
    """Multi-layer response cache for fast retrieval."""

    def __init__(self):
        self.settings = get_settings()
        self.embedding_engine = EmbeddingEngine.get_instance()
        # In-memory exact match cache for fastest lookups
        self._exact_cache: dict[str, str] = {}
        # In-memory semantic embeddings cache
        self._semantic_cache: list[dict] = []  # [{hash, embedding, response}]
        self._loaded = False

    async def initialize(self):
        """Load existing cache from database into memory."""
        if self._loaded:
            return

        db = await Database.get_instance()
        entries = await db.get_all_cache_embeddings()

        for entry in entries:
            query_hash = entry["query_hash"]
            self._exact_cache[query_hash] = entry["response_text"]

            if entry["embedding"]:
                embedding = self.embedding_engine.from_bytes(entry["embedding"])
                self._semantic_cache.append({
                    "hash": query_hash,
                    "embedding": embedding,
                    "response": entry["response_text"],
                    "query": entry["query_text"]
                })

        self._loaded = True
        logger.info(f"Cache initialized: {len(self._exact_cache)} exact, {len(self._semantic_cache)} semantic entries")

    @staticmethod
    def _hash_query(query: str) -> str:
        """Create a hash of the normalized query."""
        normalized = query.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    async def lookup(self, query: str) -> Tuple[Optional[str], str]:
        """
        Look up a query in the cache.
        Returns (response, cache_type) where cache_type is 'exact', 'semantic', or 'miss'.
        """
        query_hash = self._hash_query(query)

        # Layer 1: Exact match (instant)
        if query_hash in self._exact_cache:
            logger.info(f"Cache HIT (exact) for: {query[:50]}...")
            # Update hit count in background
            db = await Database.get_instance()
            await db.get_cached_response(query_hash)
            return self._exact_cache[query_hash], "exact"

        # Layer 2: Semantic match
        if self._semantic_cache:
            query_embedding = await self.embedding_engine.async_encode(query)

            best_score = 0.0
            best_response = None
            best_query = None

            for entry in self._semantic_cache:
                score = self.embedding_engine.cosine_similarity(
                    query_embedding, entry["embedding"]
                )
                if score > best_score:
                    best_score = score
                    best_response = entry["response"]
                    best_query = entry["query"]

            if best_score >= self.settings.cache_similarity_threshold:
                logger.info(
                    f"Cache HIT (semantic, score={best_score:.3f}) for: {query[:50]}... "
                    f"matched: {best_query[:50]}..."
                )
                return best_response, "semantic"

        logger.info(f"Cache MISS for: {query[:50]}...")
        return None, "miss"

    async def store(self, query: str, response: str):
        """Store a query-response pair in the cache."""
        query_hash = self._hash_query(query)

        # Skip if already cached
        if query_hash in self._exact_cache:
            return

        # Generate embedding
        query_embedding = await self.embedding_engine.async_encode(query)
        embedding_bytes = self.embedding_engine.to_bytes(query_embedding)

        # Store in memory
        self._exact_cache[query_hash] = response
        self._semantic_cache.append({
            "hash": query_hash,
            "embedding": query_embedding,
            "response": response,
            "query": query
        })

        # Persist to database
        db = await Database.get_instance()
        await db.save_cache_entry(query_hash, query, response, embedding_bytes)

        # Evict old entries if cache is too large
        if len(self._exact_cache) > self.settings.cache_max_size:
            await self._evict_oldest()

        logger.info(f"Cached response for: {query[:50]}...")

    async def _evict_oldest(self):
        """Remove oldest entries when cache exceeds max size."""
        # Simple strategy: remove 10% of oldest entries
        evict_count = self.settings.cache_max_size // 10
        self._semantic_cache = self._semantic_cache[evict_count:]
        # Rebuild exact cache from semantic cache
        self._exact_cache = {e["hash"]: e["response"] for e in self._semantic_cache}
        logger.info(f"Evicted {evict_count} cache entries")
