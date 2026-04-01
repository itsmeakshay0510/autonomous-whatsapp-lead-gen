"""
PHN Technology - WhatsApp AI Agent
Main application entry point.

Usage:
    python main.py

Or with uvicorn:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database.db import Database
from cache.embedding_engine import EmbeddingEngine
from cache.response_cache import ResponseCache
from agent.agent import Agent
from whatsapp.webhook import router as webhook_router, set_message_handler
from whatsapp.sender import WhatsAppSender
from tools.set_reminder import check_and_send_reminders

# ============================================
# Logging Configuration
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("phn_agent")

# ============================================
# Global Components
# ============================================
agent: Agent = None
sender: WhatsAppSender = None
_reminder_task: asyncio.Task = None


# ============================================
# Message Handler (called by webhook)
# ============================================
async def handle_incoming_message(phone: str, text: str, message_id: str = None):
    """Process an incoming WhatsApp message and send reply."""
    global agent, sender

    try:
        # Mark message as read (blue ticks)
        if message_id:
            await sender.mark_as_read(message_id)

        # Process through agent
        response = await agent.process_message(phone, text)

        # Send reply
        if response:
            await sender.send_reply(phone, response, message_id)

    except Exception as e:
        logger.error(f"Error handling message from {phone}: {e}", exc_info=True)
        # Send fallback message
        try:
            await sender.send_text(
                phone,
                "I apologize for the inconvenience! 🙏 "
                "Our system is experiencing a brief issue. "
                "Please try again in a moment, or type 'hi' to restart."
            )
        except Exception:
            pass


# ============================================
# Reminder Scheduler
# ============================================
async def reminder_loop():
    """Background task that checks for due reminders every 60 seconds."""
    global sender
    while True:
        try:
            await asyncio.sleep(60)
            await check_and_send_reminders(sender.send_text)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")


# ============================================
# Application Lifespan
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global agent, sender, _reminder_task

    settings = get_settings()
    logger.info("=" * 60)
    logger.info("  PHN Technology — WhatsApp AI Agent Starting...")
    logger.info("=" * 60)

    # 1. Initialize database
    logger.info("[1/5] Initializing database...")
    await Database.get_instance()

    # 2. Load embedding model
    logger.info("[2/5] Loading embedding model...")
    embedding_engine = EmbeddingEngine.get_instance()
    embedding_engine.load()

    # 3. Initialize agent
    logger.info("[3/5] Initializing AI agent...")
    agent = Agent()
    await agent.initialize()

    # 4. Initialize WhatsApp sender
    logger.info("[4/5] Initializing WhatsApp sender...")
    sender = WhatsAppSender()

    # 5. Set up webhook handler
    logger.info("[5/5] Setting up webhook handler...")
    set_message_handler(handle_incoming_message)

    # Start reminder scheduler
    _reminder_task = asyncio.create_task(reminder_loop())

    logger.info("=" * 60)
    logger.info(f"  ✅ Agent ready! Model: {settings.ollama_model}")
    logger.info(f"  🌐 Server: http://{settings.server_host}:{settings.server_port}")
    logger.info(f"  📡 Webhook: http://{settings.server_host}:{settings.server_port}/webhook")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down...")
    if _reminder_task:
        _reminder_task.cancel()
        try:
            await _reminder_task
        except asyncio.CancelledError:
            pass

    if sender:
        await sender.close()

    db = await Database.get_instance()
    await db.close()

    logger.info("Agent shutdown complete.")


# ============================================
# FastAPI Application
# ============================================
app = FastAPI(
    title="PHN Technology WhatsApp Agent",
    description="AI-powered WhatsApp assistant for PHN Technology course inquiries and registration",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include webhook router
app.include_router(webhook_router)


# ============================================
# Health Check & Utility Endpoints
# ============================================
@app.get("/")
async def root():
    return {
        "service": "PHN Technology WhatsApp Agent",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from agent.llm_client import LLMClient

    llm = LLMClient.get_instance()
    model_ok = await llm.check_health()

    return {
        "status": "healthy" if model_ok else "degraded",
        "model": get_settings().ollama_model,
        "model_loaded": model_ok,
    }


@app.post("/test")
async def test_message(phone: str = "test_user", message: str = "hello"):
    """
    Test endpoint — send a message to the agent without WhatsApp.
    Useful for development and testing.

    Usage: POST /test?phone=test123&message=what+courses+do+you+offer
    """
    global agent

    if agent is None:
        return {"error": "Agent not initialized"}

    response = await agent.process_message(phone, message)
    return {"phone": phone, "message": message, "response": response}


# ============================================
# Entry Point
# ============================================
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,  # Set to True for development
        log_level="info",
        workers=1,  # Single worker for Ollama (model loaded once)
    )
