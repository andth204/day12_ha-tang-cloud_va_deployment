"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (10 req/min per user)
  ✅ Cost guard ($10/month per user)
  ✅ Conversation history (Redis-backed, in-memory fallback)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Stateless design (state trong Redis)
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import time
import signal
import logging
import json
from collections import defaultdict
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_and_record_cost

from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Conversation History — Redis-backed, in-memory fallback
# ─────────────────────────────────────────────────────────
_redis = None
_memory_history: dict[str, list] = defaultdict(list)  # fallback

def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    if not settings.redis_url:
        return None
    try:
        import redis
        r = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        _redis = r
        logger.info(json.dumps({"event": "redis_connected", "url": settings.redis_url}))
    except Exception as e:
        logger.warning(json.dumps({"event": "redis_unavailable", "reason": str(e)}))
        _redis = None
    return _redis

def load_history(user_id: str, limit: int = 10) -> list[dict]:
    r = _get_redis()
    if r:
        raw = r.lrange(f"history:{user_id}", -limit * 2, -1)
        history = []
        for i in range(0, len(raw) - 1, 2):
            history.append({"role": "user", "content": raw[i]})
            history.append({"role": "assistant", "content": raw[i + 1]})
        return history
    return _memory_history[user_id][-(limit * 2):]

def save_history(user_id: str, question: str, answer: str):
    r = _get_redis()
    if r:
        key = f"history:{user_id}"
        r.rpush(key, question, answer)
        r.expire(key, 86400)  # TTL 24h
    else:
        _memory_history[user_id].extend([question, answer])
        _memory_history[user_id] = _memory_history[user_id][-20:]  # keep last 10 turns

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    _get_redis()  # try connecting early
    time.sleep(0.1)
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(None, description="Optional session ID for conversation history")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str
    history_count: int = 0

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    **Conversation history:** Pass `user_id` in body to maintain session context.
    """
    user_id = body.user_id or api_key[:8]

    # Rate limit per user
    check_rate_limit(user_id)

    # Budget check (per-user, monthly)
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(user_id, input_tokens, 0)

    # Load conversation history
    history = load_history(user_id)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": user_id,
        "q_len": len(body.question),
        "history_turns": len(history) // 2,
    }))

    answer = llm_ask(body.question)

    # Save to history
    save_history(user_id, body.question, answer)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(user_id, 0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
        history_count=len(history) // 2 + 1,
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    r = _get_redis()
    checks = {
        "llm": "mock" if not settings.openai_api_key else "openai",
        "storage": "redis" if r else "in-memory",
    }
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(api_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "storage": "redis" if _get_redis() else "in-memory",
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
