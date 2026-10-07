"""
legal_ai/config.py

Centralized configuration, environment management, and infrastructure client
singletons (Supabase, Pinecone, Anthropic, Voyage AI) for the Pakistani Legal AI platform.
Establishes the Single Source of Truth for system credentials, model definitions,
and robust API wrapper helpers.
"""

import os
import sys
import time
import re
from typing import List, Dict, Any, Optional, Set
import httpx
from dotenv import load_dotenv

# Ensure environment is loaded from repository root .env
load_dotenv()

# --- Runtime Environment & Production Detection ---
_env_val = os.environ.get("ENVIRONMENT", "").strip().lower()
IS_PRODUCTION: bool = _env_val not in ("development", "dev", "test")

# --- Model & Synthesis Settings ---
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_FALLBACK_MODEL: str = os.environ.get("ANTHROPIC_FALLBACK_MODEL", "").strip()
MAX_SYNTHESIS_TOKENS: int = int(os.environ.get("MAX_SYNTHESIS_TOKENS", "8192"))

# --- Pinecone Vector Database Config ---
PINECONE_API_KEY: Optional[str] = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME: str = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
PINECONE_NAMESPACE: str = os.environ.get("PINECONE_NAMESPACE", "judgments")
if not PINECONE_NAMESPACE or PINECONE_NAMESPACE == "default":
    PINECONE_NAMESPACE = "judgments"
PINECONE_HOST: str = os.environ.get(
    "PINECONE_HOST",
    "https://legal-kb-pk-local-uc3rhld.svc.aped-4627-b74a.pinecone.io"
)

# --- Supabase Database & Storage Config ---
SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY: Optional[str] = os.environ.get("SUPABASE_SERVICE_KEY")

# --- Anthropic LLM Config ---
ANTHROPIC_API_KEY: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
_raw_ws = (os.environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()
if _raw_ws and _raw_ws.startswith("wrkspc_"):
    ANTHROPIC_WORKSPACE_ID: Optional[str] = _raw_ws
else:
    ANTHROPIC_WORKSPACE_ID: Optional[str] = "wrkspc_016AwCn1LDaCtQ39UsfQiWjU"

# --- Voyage AI Embedding Config ---
VOYAGE_API_KEY: Optional[str] = os.environ.get("VOYAGE_API_KEY")
VOYAGE_API_URL: str = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL: str = "voyage-law-2"

# --- CORS & Base URL ---
ALLOWED_ORIGINS: List[str] = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# Client singletons (lazy loaded / cached)
_supabase_client = None
_pinecone_index = None
_async_anthropic_client = None


def get_backend_base_url() -> str:
    """Resolves canonical backend base URL for public links and PDF endpoints."""
    domain = (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("RAILWAY_STATIC_URL")
        or os.environ.get("PUBLIC_DOMAIN")
    )
    if domain:
        domain = domain.strip()
        if not domain.startswith("http://") and not domain.startswith("https://"):
            return f"https://{domain}"
        return domain
    return "https://lawyer-backend-production-26c7.up.railway.app"


def get_authorized_testers() -> Set[str]:
    """Retrieves authorized testers set for fail-closed prototype gates."""
    custom = os.environ.get("AUTHORIZED_TESTERS")
    if custom is not None:
        if not custom.strip():
            return set()
        return {t.strip() for t in custom.split(",") if t.strip()}
    return {"*"}


# --- Supabase Client Management ---
def get_supabase_client():
    """Returns singleton Supabase client with lazy initialization."""
    global _supabase_client
    if _supabase_client is None and SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            from supabase import create_client
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        except Exception as launch_err:
            print(f"⚠️ [legal_ai.config] Supabase init warning: {launch_err}", file=sys.stderr, flush=True)
    return _supabase_client


def safe_supabase_query(query_fn, retries: int = 4):
    """
    Executes a Supabase query with automatic client re-initialization and retry
    if a stale connection (ConnectionTerminated, connection reset, etc.) is encountered.
    """
    global _supabase_client
    for attempt in range(retries):
        try:
            return query_fn()
        except Exception as e:
            err_str = str(e)
            if "ConnectionTerminated" in err_str or "connection" in err_str.lower() or attempt < retries - 1:
                print(
                    f"⚠️ [legal_ai.config] Supabase query retry (attempt {attempt+1}/{retries}): {err_str}",
                    file=sys.stderr,
                    flush=True
                )
                time.sleep(0.5 * (attempt + 1))
                try:
                    from supabase import create_client
                    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
                except Exception:
                    pass
                continue
            raise e


# --- Pinecone Client Management ---
def get_pinecone_index():
    """Returns singleton Pinecone index instance."""
    global _pinecone_index
    if _pinecone_index is None and PINECONE_API_KEY:
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=PINECONE_API_KEY)
            try:
                _pinecone_index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)
            except Exception:
                _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
        except Exception as launch_err:
            print(f"⚠️ [legal_ai.config] Pinecone init warning: {launch_err}", file=sys.stderr, flush=True)
    return _pinecone_index


# --- Anthropic Client Management ---
def get_anthropic_client():
    """Returns singleton AsyncAnthropic client with optional LangSmith tracing wrapper."""
    global _async_anthropic_client
    if _async_anthropic_client is None and ANTHROPIC_API_KEY:
        try:
            from anthropic import AsyncAnthropic
            anthropic_headers = {}
            if ANTHROPIC_WORKSPACE_ID:
                anthropic_headers["anthropic-workspace-id"] = ANTHROPIC_WORKSPACE_ID
            raw_client = AsyncAnthropic(
                api_key=ANTHROPIC_API_KEY,
                default_headers=anthropic_headers if anthropic_headers else None
            )
            try:
                from langsmith import wrappers
                _async_anthropic_client = wrappers.wrap_anthropic(raw_client)
            except Exception:
                _async_anthropic_client = raw_client
        except Exception as launch_err:
            print(f"⚠️ [legal_ai.config] Anthropic client init warning: {launch_err}", file=sys.stderr, flush=True)
    return _async_anthropic_client


async def safe_create_anthropic_message(**kwargs):
    """
    Central, robust Anthropic API caller.
    Features:
    - Centralized access across all modules without circular imports.
    - Automatic token bounding (MAX_SYNTHESIS_TOKENS).
    - SDK temperature parameter compatibility.
    - Automatic fallback model failover if primary model returns 404 / not_found.
    """
    from fastapi import HTTPException
    client = get_anthropic_client()
    if not client:
        raise HTTPException(status_code=503, detail="Anthropic API client is not initialized.")

    primary_model = kwargs.get("model") or CLAUDE_MODEL
    call_kwargs = dict(kwargs)
    call_kwargs["model"] = primary_model

    if "max_output_tokens" in call_kwargs:
        call_kwargs["max_tokens"] = call_kwargs.pop("max_output_tokens")
    if "max_tokens" not in call_kwargs:
        call_kwargs["max_tokens"] = MAX_SYNTHESIS_TOKENS

    if "temperature" in call_kwargs:
        temp_val = call_kwargs.pop("temperature")
        extra_body = dict(call_kwargs.get("extra_body") or {})
        extra_body["temperature"] = temp_val
        call_kwargs["extra_body"] = extra_body

    try:
        return await client.messages.create(**call_kwargs)
    except Exception as e:
        err_str = str(e)

        # 1. Immediate Auto-Recovery for Workspace Header Errors
        if "workspace" in err_str.lower() and ("not found" in err_str.lower() or "invalid" in err_str.lower()):
            print(
                f"⚠️ [legal_ai.config] Anthropic rejected workspace ID. "
                f"Auto-recovering with default workspace 'wrkspc_016AwCn1LDaCtQ39UsfQiWjU'...",
                file=sys.stderr,
                flush=True
            )
            try:
                from anthropic import AsyncAnthropic
                recov_client = AsyncAnthropic(
                    api_key=ANTHROPIC_API_KEY,
                    default_headers={"anthropic-workspace-id": "wrkspc_016AwCn1LDaCtQ39UsfQiWjU"}
                )
                return await recov_client.messages.create(**call_kwargs)
            except Exception as recov_err:
                print(f"⚠️ [legal_ai.config] Workspace recovery attempt failed: {recov_err}. Trying without workspace header...", file=sys.stderr, flush=True)
                recov_client_no_hdr = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
                return await recov_client_no_hdr.messages.create(**call_kwargs)

        # 2. Model 404 Failover (Only when error is specifically about model, not workspace)
        is_model_error = ("model:" in err_str.lower() or "model_not_found" in err_str.lower() or ("404" in err_str and "model" in err_str.lower())) and "workspace" not in err_str.lower()
        if not is_model_error:
            raise e

        candidate_models = []
        if ANTHROPIC_FALLBACK_MODEL:
            candidate_models.append(ANTHROPIC_FALLBACK_MODEL)
        for m in ["claude-haiku-4-5-20251001"]:
            if m not in candidate_models and m != primary_model:
                candidate_models.append(m)

        for fallback_model in candidate_models:
            print(
                f"⚠️ [legal_ai.config] Anthropic model '{primary_model}' returned 404/not_found. "
                f"Attempting fallback model '{fallback_model}'...",
                file=sys.stderr,
                flush=True
            )
            try:
                fallback_kwargs = dict(call_kwargs)
                fallback_kwargs["model"] = fallback_model
                return await client.messages.create(**fallback_kwargs)
            except Exception as fallback_err:
                fb_str = str(fallback_err)
                if not ("404" in fb_str or "not_found" in fb_str.lower() or "model:" in fb_str.lower()):
                    raise fallback_err
                continue

        raise RuntimeError(
            f"Anthropic API Model Access Error: Model '{primary_model}' is not accessible with configured ANTHROPIC_API_KEY. "
            f"Set ANTHROPIC_FALLBACK_MODEL or verify permissions in Anthropic Console. Original error: {e}"
        ) from e


# --- Voyage Embedding Helper ---
async def get_voyage_embedding(text: str) -> List[float]:
    """Fetches 1024-dimension dense embedding vector using voyage-law-2."""
    from fastapi import HTTPException
    if not VOYAGE_API_KEY:
        raise HTTPException(status_code=500, detail="VOYAGE_API_KEY is missing from environment.")
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json"
    }
    clean_input = text[:4000] if text else ""
    payload = {
        "input": [clean_input],
        "model": VOYAGE_MODEL
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(VOYAGE_API_URL, headers=headers, json=payload)
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Voyage AI embedding error: {res.text}")
        data = res.json()
        return data["data"][0]["embedding"]
