import os
import sys
import uuid
from fastapi import FastAPI, HTTPException, status, Depends, Response, BackgroundTasks, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, cast
import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from pinecone import Pinecone
from anthropic import AsyncAnthropic
import re
import json
from supabase import create_client, Client
from dotenv import load_dotenv

# Load local environment testing overrides
load_dotenv()

# 🛡️ SENTRY SYSTEM LOG ENGINE: Production exception diagnostics activation
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(title="AMICUS AI - Production Serverless Clerk-Secure Engine")

# 🔒 DYNAMIC CORS CORE MIDDLEWARE: Completely bypasses origin restrictions by safely mirroring
# request origins, resolving all 400 Bad Request and preflight mismatch issues on Lovable.
@app.middleware("http")
async def dynamic_cors_middleware(request, call_next):
    origin = request.headers.get("origin")
    
    # Intercept and handle OPTIONS preflight requests directly
    if request.method == "OPTIONS" and origin:
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        
        # Dynamically mirror requested headers to ensure no preflight fails
        req_headers = request.headers.get("access-control-request-headers")
        if req_headers:
            response.headers["Access-Control-Allow-Headers"] = req_headers
        else:
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, X-Requested-With, Clerk-Auth-Token"
            
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    response = await call_next(request)
    
    # Mirror origin to browser client for standard requests
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        
        req_headers = request.headers.get("access-control-request-headers")
        if req_headers:
            response.headers["Access-Control-Allow-Headers"] = req_headers
        else:
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept, X-Requested-With, Clerk-Auth-Token"
        
    return response

# ----------------------------------------------------------------------
# Production Environment Variable Guard Checks
# ----------------------------------------------------------------------
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# Initialize Cloud Infrastructures gracefully with fallback logging to prevent Railway build crashes
pinecone_index = None
if PINECONE_API_KEY:
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    except Exception as launch_err:
        print(f"⚠️ Pinecone startup warning: {launch_err}")
else:
    print("⚠️ WARNING: PINECONE_API_KEY environment variable is missing!")

supabase: Any = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as launch_err:
        print(f"⚠️ Supabase startup warning: {launch_err}")
else:
    print("⚠️ WARNING: Supabase database connection tokens are missing!")

# Initialize Anthropic Client conditionally to support fallback simulations
async_anthropic_client = None
if ANTHROPIC_API_KEY:
    try:
        raw_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        try:
            from langsmith import wrappers
            async_anthropic_client = wrappers.wrap_anthropic(raw_client)
            print("LangSmith wrapping initialized on Anthropic client.")
        except Exception as e:
            async_anthropic_client = raw_client
            print(f"Running Anthropic client without LangSmith wrapper: {e}")
    except Exception as launch_err:
        print(f"Anthropic client startup warning: {launch_err}")
else:
    print("⚠️ WARNING: ANTHROPIC_API_KEY is missing. Activating LLM Simulation Fallback Layer for testing.")

# Security token interceptor (with auto_error=False to catch empty headers smoothly)
security_agent = HTTPBearer(auto_error=False)

# Global cache memory to keep token authorization verification ultra-fast
_clerk_jwks_keys_cache = None

# ----------------------------------------------------------------------
# Authentication & Authorization Hook Dependencies
# ----------------------------------------------------------------------
async def verify_clerk_session(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_agent)) -> str:
    """
    🔐 DYNAMIC CLERK PRODUCTION BOUNDARY: Extracts incoming bearer tokens,
    authenticates signatures against Clerk's secure JWKS cache, and returns user ID.
    """
    global _clerk_jwks_keys_cache
    
    if not credentials:
        print("❌ [AUTH MONITOR] Validation Failed: The Authorization header is completely MISSING!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Access Denied: Request missing Authorization bearer token."
        )
        
    token = credentials.credentials

    clerk_secret = os.environ.get("CLERK_SECRET_KEY")
    # Local fallback bypass for isolated testing environments if secret is missing or mock token is sent
    if not clerk_secret or token == "mock_clerk_user_id_dev_run":
        return "mock_clerk_user_id_dev_run"
        
    try:
        unverified_header = jwt.get_unverified_header(token)
        if not isinstance(unverified_header, dict):
            print("❌ [AUTH MONITOR] Validation Failed: Token header layout is not a structured dictionary.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature layout shape.")
            
        kid = unverified_header.get("kid")
        if not kid:
            print("❌ [AUTH MONITOR] Validation Failed: Token header is missing a Key ID ('kid').")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature architecture layout.")
            
        if not _clerk_jwks_keys_cache:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {clerk_secret}"}
                jwks_response = await client.get("https://api.clerk.com/v1/jwks", headers=headers)
                if jwks_response.status_code != 200:
                    print(f"❌ [AUTH MONITOR] Keyserver Error: Clerk rejected handshake with code {jwks_response.status_code}")
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to sync signature pairs from Clerk.")
                _clerk_jwks_keys_cache = jwks_response.json().get("keys", [])
                
        public_key = None
        if _clerk_jwks_keys_cache:
            for key_data in _clerk_jwks_keys_cache:
                if isinstance(key_data, dict) and key_data.get("kid") == kid:
                    public_key = RSAAlgorithm.from_jwk(key_data)
                    break
                
        if not public_key:
            print("❌ [AUTH MONITOR] Validation Failed: The token 'kid' does not match cached Clerk keys.")
            _clerk_jwks_keys_cache = None  # Flush cache to force re-fetch
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Stale authentication signature validation parameters.")
            
        decoded_payload = jwt.decode(
            token,
            key=cast(Any, public_key),
            algorithms=["RS256"],
            options={"verify_aud": False},
            leeway=60
        )
        
        user_id = decoded_payload.get("sub")
        if not user_id:
            print("❌ [AUTH MONITOR] Validation Failed: Token parsed successfully but lacks a subject ('sub').")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile subject reference claim is missing.")
            
        return str(user_id)
        
    except jwt.exceptions.ExpiredSignatureError as e:
        print(f"❌ [AUTH MONITOR] Cryptographic Denial: Token is expired. Details: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed: The provided session token has expired.")
    except Exception as error_context:
        print(f"❌ [AUTH MONITOR] Cryptographic Denial: Core verification dropped. Context: {str(error_context)}")
        raise HTTPException(status_code=401, detail=f"Access Denied: Token signature verification dropped: {str(error_context)}")

async def verify_admin_role(authenticated_user_id: str = Depends(verify_clerk_session)) -> str:
    """
    🛡️ ADMIN ROLE GUARD: Cross-references the authenticated Clerk user ID against
    the Supabase user database role configuration to confirm administrative clearance.
    """
    if authenticated_user_id == "mock_clerk_user_id_dev_run":
        return authenticated_user_id
        
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection is currently offline.")
    profile_query = supabase.table("users").select("role").eq("id", authenticated_user_id).execute()
    if profile_query.data and len(profile_query.data) > 0:
        first_row = profile_query.data[0]
        if isinstance(first_row, dict):
            user_role = first_row.get("role")
            if user_role == "admin":
                return authenticated_user_id
            
    print(f"🚫 [SECURITY ALERT] Unauthorized Access Attempt to Admin endpoint by user {authenticated_user_id}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access Denied: This operation requires administrative account permissions."
    )

# ----------------------------------------------------------------------
# Data Transport Verification Forms (Pydantic Models)
# ----------------------------------------------------------------------
class UserSyncPayload(BaseModel):
    email: str
    full_name: str

class ProfileUpdatePayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str

class AccessRegistration(BaseModel):
    full_name: str
    firm_name: str
    email: str

class AssociateCreatePayload(BaseModel):
    full_name: str
    email: str
    status: str = "admin_approved"

class AssociateStatusPayload(BaseModel):
    status: str

class ImagePayload(BaseModel):
    image_base64: str
    image_mime_type: str

class QueryRequest(BaseModel):
    query_text: str
    images: Optional[List[ImagePayload]] = None
    category: str = "general"

class FeedbackRequest(BaseModel):
    query_id: str
    original_answer: str
    correct_answer: str

# Category Specific Prompts for Pakistan Law
SYSTEM_PROMPTS = {
    "criminal": (
        "You are an elite Pakistani criminal law specialist, holding deep expertise in the Pakistan Penal Code (PPC) "
        "and Code of Criminal Procedure (CrPC). Answer the queries accurately citing specific sections, case precedents, "
        "and legal provisions based on the provided context."
    ),
    "divorce_family": (
        "You are a leading Pakistani family law expert, specializing in the Muslim Family Laws Ordinance, Dissolution "
        "of Muslim Marriages Act, and related child custody, dower, maintenance, and divorce jurisprudence. "
        "Answer strictly and cite appropriate Pakistani laws."
    ),
    "government_constitutional": (
        "You are a senior Pakistani constitutional law expert, specializing in civil rights, writ petitions under Article 199, "
        "civil service regulations, and administrative law. Cite Constitutional Articles and leading judgments."
    ),
    "corporate_tax": (
        "You are a Pakistani corporate and tax law advisor, specializing in the Companies Act 2017, Contract Act, SECP regulations, "
        "and income/sales tax ordinances. Provide clear, professional statutory citations."
    ),
    "land_property": (
        "You are an expert on Pakistani land revenue, transfer of property, tenancy, and registration laws (including the "
        "Land Revenue Act and Transfer of Property Act). Provide detail-oriented advice on registry, mutation, and ownership disputes."
    ),
    "general": (
        "You are an elite, highly precise Pakistani legal expert. Answer strictly based on the context data blocks provided, citing explicitly."
    )
}

# Helper to verify quotas from Supabase database logs
def check_user_quota(user_id: str, num_images_requested: int):
    if user_id == "mock_clerk_user_id_dev_run" or not supabase:
        return  # Allow dev fallback
        
    try:
        from datetime import datetime, timedelta, timezone
        time_limit = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        
        # Query matching records in last 24h
        res = supabase.table("queries").select("id", "query_text").eq("user_id", user_id).gte("created_at", time_limit).execute()
        records = res.data if res else []
        
        # Check overall daily limit (e.g., 100 queries)
        if len(records) >= 100:
            raise HTTPException(status_code=429, detail="Daily query quota limit exceeded (Max 100 queries/day).")
            
        if num_images_requested > 0:
            # We look for queries containing attachments in their logs
            vision_count = 0
            for r in records:
                # Count instances of [Vision Context] tags or query logs with attachments safely
                if isinstance(r, dict):
                    q_val = r.get("query_text", "")
                    if q_val and "[Vision Context]" in str(q_val):
                        vision_count += 1
            if vision_count >= 30:
                raise HTTPException(status_code=429, detail="Daily document upload/vision limit exceeded (Max 30 queries with images/day).")
    except HTTPException:
        raise
    except Exception as e:
        print(f"⚠️ Quota verification error: {e}")

# ----------------------------------------------------------------------
# Core Operation Controllers (Existing Workflows)
# ----------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/request-access")
async def register_access_request(request: AccessRegistration):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database service is currently offline.")
    try:
        duplicate_check = supabase.table("access_requests").select("id").eq("email", request.email).execute()
        if duplicate_check.data and len(duplicate_check.data) > 0:
            return {"status": "duplicate", "message": "An invitation request for this email address is already under review."}
            
        supabase.table("access_requests").insert({
            "full_name": request.full_name,
            "firm_name": request.firm_name,
            "email": request.email,
            "status": "pending"
        }).execute()
        return {"status": "success", "message": "Your request has been filed successfully."}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/sync")
async def sync_clerk_user_profile(payload: UserSyncPayload, authenticated_user_id: str = Depends(verify_clerk_session)):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database service is currently offline.")
    try:
        # 1. Check if user already exists by authenticated Clerk ID
        profile_query = supabase.table("users").select("*").eq("id", authenticated_user_id).execute()
        if profile_query.data and len(profile_query.data) > 0:
            existing_user = profile_query.data[0]
            # Auto-sync profile info if modified in Clerk/App
            if existing_user.get("full_name") != payload.full_name or existing_user.get("email") != payload.email:
                updated_profile = supabase.table("users").update({
                    "full_name": payload.full_name,
                    "email": payload.email
                }).eq("id", authenticated_user_id).execute()
                return {"status": "updated", "user": updated_profile.data[0]}
            return {"status": "exists", "user": existing_user}
            
        # 2. Check if user already exists by Email (handles legacy/mock accounts transition)
        email_query = supabase.table("users").select("*").eq("email", payload.email).execute()
        if email_query.data and len(email_query.data) > 0:
            legacy_user = email_query.data[0]
            if isinstance(legacy_user, dict):
                legacy_id = legacy_user.get("id")
                legacy_role = legacy_user.get("role", "associate")
                if legacy_id and legacy_id != authenticated_user_id:
                    print(f"🔄 Resolving legacy account migration from '{legacy_id}' to '{authenticated_user_id}'...", file=sys.stderr)
                    # A. Rename email on legacy mock user to free the unique constraint
                    temp_email = f"legacy-{legacy_id}-{payload.email}"
                    supabase.table("users").update({"email": temp_email}).eq("id", legacy_id).execute()
                    
                    # B. Insert new authenticated user record
                    inserted_profile = supabase.table("users").insert({
                        "id": authenticated_user_id,
                        "email": payload.email,
                        "full_name": payload.full_name,
                        "role": legacy_role
                    }).execute()
                    
                    # C. Migrate dependent foreign key references safely now that authenticated ID exists in users table
                    try:
                        supabase.table("queries").update({"user_id": authenticated_user_id}).eq("user_id", legacy_id).execute()
                        supabase.table("feedback").update({"user_id": authenticated_user_id}).eq("user_id", legacy_id).execute()
                        try:
                            supabase.table("activity_log").update({"user_id": authenticated_user_id}).eq("user_id", legacy_id).execute()
                        except Exception:
                            pass
                    except Exception as ref_err:
                        print(f"⚠️ References migration warning: {ref_err}", file=sys.stderr)
                    
                    # D. Purge legacy mock user from users table
                    try:
                        supabase.table("users").delete().eq("id", legacy_id).execute()
                    except Exception as del_err:
                        print(f"⚠️ Could not delete legacy user record: {del_err}", file=sys.stderr)
                        
                    return {"status": "updated", "user": inserted_profile.data[0]}
            
        # 3. If new user, check access request approvals
        access_check = supabase.table("access_requests").select("status").eq("email", payload.email).execute()
        assigned_role = "pending" # Default to pending to restrict unapproved users
        if access_check.data and len(access_check.data) > 0:
            first_access = access_check.data[0]
            if isinstance(first_access, dict):
                status_val = first_access.get("status")
                if status_val == "admin_approved":
                    assigned_role = "admin"
                elif status_val in ("approved", "associate_approved"):
                    assigned_role = "associate"

        inserted_profile = supabase.table("users").insert({
            "id": authenticated_user_id,
            "email": payload.email,
            "full_name": payload.full_name,
            "role": assigned_role
        }).execute()
        return {"status": "created", "user": inserted_profile.data[0]}
    except Exception as e:
        import traceback
        print("❌ [USERS/SYNC ERROR]:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/quota")
async def get_user_quota_status(authenticated_user_id: str = Depends(verify_clerk_session)):
    """
    📊 USER QUOTA ENDPOINT: Computes usage statistics (remaining queries/images)
    and quota reset time for the authenticated user.
    """
    if not supabase:
        return {
            "text_queries_used": 0,
            "text_queries_limit": 100,
            "text_queries_remaining": 100,
            "vision_queries_used": 0,
            "vision_queries_limit": 30,
            "vision_queries_remaining": 30,
            "reset_time_iso": None
        }
    try:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        time_limit = (now - timedelta(hours=24)).isoformat()
        
        res = supabase.table("queries").select("created_at", "query_text").eq("user_id", authenticated_user_id).gte("created_at", time_limit).execute()
        records = res.data if res else []
        
        total_used = len(records)
        vision_used = 0
        oldest_query_time = None
        
        for r in records:
            if isinstance(r, dict):
                q_val = r.get("query_text", "")
                if q_val and "[Vision Context]" in str(q_val):
                    vision_used += 1
                
                created_str = r.get("created_at")
                if created_str:
                    try:
                        created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                        if oldest_query_time is None or created_dt < oldest_query_time:
                            oldest_query_time = created_dt
                    except Exception:
                        pass
        
        reset_time = None
        if oldest_query_time:
            reset_time = (oldest_query_time + timedelta(hours=24)).isoformat()
            
        return {
            "text_queries_used": total_used,
            "text_queries_limit": 100,
            "text_queries_remaining": max(0, 100 - total_used),
            "vision_queries_used": vision_used,
            "vision_queries_limit": 30,
            "vision_queries_remaining": max(0, 30 - vision_used),
            "reset_time_iso": reset_time
        }
    except Exception as e:
        print(f"⚠️ Error fetching user quota: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quota status.")

# ----------------------------------------------------------------------
# Asynchronous Query Job Store and Runner
# ----------------------------------------------------------------------
jobs_store: Dict[str, Dict[str, Any]] = {}

def cleanup_old_jobs():
    try:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        expiry = timedelta(minutes=15)
        to_delete = [jid for jid, job in jobs_store.items() if now - job.get("created_at", now) > expiry]
        for jid in to_delete:
            del jobs_store[jid]
    except Exception as e:
        print(f"⚠️ Error cleaning up old jobs: {e}", file=sys.stderr)

async def process_query_job(job_id: str, request: QueryRequest, authenticated_user_id: str):
    from datetime import datetime, timezone
    try:
        print(f"🚀 [JOB {job_id}] Starting query execution...", file=sys.stderr, flush=True)
        
        # Helper to strip data-url prefixes if sent by the frontend
        def clean_base64_data(base64_str: str) -> str:
            if "," in base64_str:
                return base64_str.split(",", 1)[1]
            return base64_str.strip()

        def sanitize_mime_type(mime: str) -> str:
            m = mime.lower().strip()
            if m == "image/jpg":
                return "image/jpeg"
            return m

        def clean_repeated_phrases(text: str) -> str:
            if not text:
                return ""
            text = re.sub(r'\s+', ' ', text).strip()
            prev_text = None
            while prev_text != text:
                prev_text = text
                text = re.sub(r'\b(\w+(?:\s+\w+){0,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
            return text

        def clean_court_name(court_name: str) -> str:
            if not court_name:
                return "High Court"
            court_name = court_name.strip()
            c_lower = court_name.lower()
            is_sc = any(x in c_lower for x in ("scmr", " pld sc ", " supreme "))
            court_name = re.sub(r'\b\d{4}\s+[A-Za-z]+\s+\d+\b', '', court_name, flags=re.IGNORECASE)
            court_name = re.sub(r'\b\d{4}\b', '', court_name)
            court_name = court_name.replace('-', ' ')
            court_name = re.sub(r'\s+', ' ', court_name).strip()
            c_lower = court_name.lower()
            if not court_name or c_lower in ("not specified", "unknown", "none"):
                return "Supreme Court of Pakistan" if is_sc else "High Court"
            if "supreme court" in c_lower or is_sc:
                return "Supreme Court of Pakistan"
            if "karachi high court sindh" in c_lower or "sindh high court" in c_lower or "high court sindh" in c_lower:
                return "Sindh High Court"
            if "lahore high court" in c_lower or "high court lahore" in c_lower:
                return "Lahore High Court"
            if "peshawar high court" in c_lower:
                return "Peshawar High Court"
            if "balochistan high court" in c_lower:
                return "Balochistan High Court"
            if "islamabad high court" in c_lower:
                return "Islamabad High Court"
            return court_name.title()


        # 1. Enforce Quotas
        images_list = request.images or []
        num_images = len(images_list)
        check_user_quota(authenticated_user_id, num_images_requested=num_images)

        has_image = num_images > 0
        extracted_doc_text = ""
        search_keywords_query = request.query_text
        
        # 2. Process images with Claude Vision to extract text & English keywords if present
        vision_input_tokens = 0
        vision_output_tokens = 0
        if has_image:
            if not async_anthropic_client or not ANTHROPIC_API_KEY:
                extracted_doc_text = f"[Simulated Urdu/English Transcript content for {num_images} attachments]"
                search_keywords_query = f"transcribed case keywords {request.query_text}"
                print("⚠️ Vision simulation triggered (missing API Key)")
            else:
                print(f"👁️ Processing {num_images} attached document pages with Claude Vision...", file=sys.stderr, flush=True)

                # Add all image blocks
                vision_content = []
                for img in images_list:
                    vision_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": sanitize_mime_type(img.image_mime_type),
                            "data": clean_base64_data(img.image_base64)
                        }
                    })
                
                # Call Claude to extract keywords only (extremely fast call)
                vision_prompt = (
                    "Identify and list 3 to 5 key legal search terms/keywords in English "
                    "from these image(s) to help search a database. Return ONLY the keywords "
                    "separated by spaces. Do not write any other text or explanation."
                )
                vision_content.append({
                    "type": "text",
                    "text": vision_prompt
                })
                
                vision_kwargs = {
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 200, # Very small tokens for speed
                    "messages": [
                        {
                            "role": "user",
                            "content": vision_content
                        }
                    ]
                }
                if os.environ.get("LANGCHAIN_API_KEY"):
                    vision_kwargs["langsmith_extra"] = {
                        "metadata": {
                            "user_id": authenticated_user_id,
                            "job_id": job_id,
                            "task": "vision_keyword_extraction"
                        }
                    }
                vision_message = await async_anthropic_client.messages.create(**vision_kwargs)
                
                if hasattr(vision_message, "usage") and vision_message.usage:
                    vision_input_tokens = getattr(vision_message.usage, "input_tokens", 0) or 0
                    vision_output_tokens = getattr(vision_message.usage, "output_tokens", 0) or 0
                
                raw_response = ""
                for block in vision_message.content:
                    block_text = getattr(block, "text", "")
                    if block_text:
                        raw_response += block_text
                        
                search_keywords_query = f"{raw_response.strip()} {request.query_text}".strip()
                extracted_doc_text = "[Full transcription and English translation generated dynamically in the final answer below]"

        # 3. Mode Classification & Precise Citation Extraction
        mode = "simple_query"
        query_lower = request.query_text.lower()
        
        # Check for citation matches (e.g. "pld 2016 sc 401")
        citation_pattern = r"\b(pld|scmr|mld|ylr|pcrli|pcrlj)\b"
        has_citation = re.search(citation_pattern, query_lower)
        
        target_citation = None
        if has_citation:
            mode = "judgment_lookup"
            # Extract standard citation patterns: e.g. "PLD 2016 SC 401"
            cit_match = re.search(r"\b((?:pld|scmr|mld|ylr|pcrli|pcrlj)\s+\d{4}\s+(?:sc|lahore|karachi|peshawar|sindh|islamabad|balochistan)?\s*\d+)\b", query_lower)
            if cit_match:
                target_citation = cit_match.group(1).upper()
        elif any(k in query_lower for k in ["draft", "petition", "bail application", "plaint", "written statement", "suit for"]):
            mode = "drafting"
        elif has_image or any(k in query_lower for k in ["analyze", "contract", "fir", "agreement", "document"]):
            mode = "document_analysis"
        elif any(k in query_lower for k in ["case law", "precedent", "ruling", "judgment of", "ruling related to"]):
            mode = "caselaw_search"
            
        print(f"⚙️ [JOB {job_id}] Query routed to: {mode}", file=sys.stderr, flush=True)

        # 4. Pinecone Vector Search
        bge_query_text = f"Represent this sentence for searching relevant passages: {search_keywords_query}"
        hf_api_url = "https://router.huggingface.co/hf-inference/models/BAAI/bge-large-en-v1.5/pipeline/feature-extraction"
        
        hf_headers = {}
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
        if hf_token:
            hf_headers["Authorization"] = f"Bearer {hf_token}"

        print("🌐 [CHECKPOINT 2] Attempting connection to Hugging Face Inference API...", file=sys.stderr, flush=True)
        async with httpx.AsyncClient(timeout=30.0) as client:
            hf_response = await client.post(hf_api_url, json={"inputs": bge_query_text}, headers=hf_headers)
            if hf_response.status_code != 200:
                raise Exception(f"Hugging Face Inference Engine failure: {hf_response.text}")
            query_vector = hf_response.json()

        print("🌲 [CHECKPOINT 3] Attempting connection to Pinecone Vector Index...", file=sys.stderr, flush=True)
        if not pinecone_index:
            raise Exception("Pinecone serverless engine index connection is inactive.")
            
        # Fetch candidate matches
        query_top_k = 25
        pinecone_kwargs = {
            "namespace": "judgments",
            "vector": query_vector,
            "top_k": query_top_k,
            "include_metadata": True
        }
        
        # If we have a precise target citation, filter by it directly in Pinecone
        raw_matches = None
        if target_citation:
            try:
                print(f"🔍 Performing precise metadata query for citation: {target_citation}", file=sys.stderr, flush=True)
                raw_matches = pinecone_index.query(filter={"citation": {"$eq": target_citation}}, **pinecone_kwargs)
            except Exception as filter_err:
                print(f"⚠️ Pinecone metadata filter warning: {filter_err}", file=sys.stderr, flush=True)
        
        if not raw_matches or not raw_matches.get("matches"):
            raw_matches = pinecone_index.query(**pinecone_kwargs)
        
        context_segments = []
        citations_payload = []
        
        matches_list = []
        if isinstance(raw_matches, dict):
            matches_list = raw_matches.get("matches", [])
        elif hasattr(raw_matches, "matches"):
            matches_list = getattr(raw_matches, "matches", []) or []
            
        # Differentiate bot outputs by prioritizing category-specific citations
        def prioritize_matches_by_bot(matches: list, category: str) -> list:
            if not category or category == "general":
                return matches
            
            cat_lower = category.lower()
            priority = []
            others = []
            
            for m in matches:
                meta = {}
                if isinstance(m, dict):
                    meta = m.get("metadata", {}) or {}
                elif hasattr(m, "metadata"):
                    meta = getattr(m, "metadata", {}) or {}
                
                citation = str(meta.get('citation', '')).lower()
                court = str(meta.get('court', '')).lower()
                subject = str(meta.get('subject_matter', '')).lower()
                title = str(meta.get('title', '')).lower()
                text = str(meta.get('text', '')).lower()
                
                is_match = False
                if cat_lower == "criminal":
                    if "pcrlj" in citation or "criminal" in subject or "criminal" in text or "cr." in citation or "murder" in text or "crpc" in text or "ppc" in text:
                        is_match = True
                elif cat_lower == "divorce_family":
                    if "clc" in citation or "mld" in citation or any(k in subject or k in text or k in title for k in ["divorce", "family", "marriage", "dower", "maintenance", "custody"]):
                        is_match = True
                elif cat_lower == "corporate_tax":
                    if "cld" in citation or "ptd" in citation or any(k in subject or k in text for k in ["tax", "corporate", "income tax", "companies act", "secp"]):
                        is_match = True
                elif cat_lower == "government_constitutional":
                    if "pld" in citation or "scmr" in citation or any(k in subject or k in text for k in ["constitution", "writ petition", "article 199", "fundamental rights"]):
                        is_match = True
                
                if is_match:
                    priority.append(m)
                else:
                    others.append(m)
            return priority + others

        # Prioritize matches
        prioritized_matches = prioritize_matches_by_bot(matches_list, request.category)
        
        # Deduplicate matches by case_id/citation, filter out unverified records, enforce 0.70 threshold, and apply generous category filtering
        seen_case_ids = set()
        seen_citations = set()
        filtered_matches = []
        
        cat_lower = request.category.lower() if request.category else "general"
        
        # Keywords to identify category relevance for generous filtering
        category_keywords = {
            "criminal": ["criminal", "cr.p.c", "ppc", "bail", "fir", "police", "offence", "accused", "trial", "sentence", "arrest", "suspect"],
            "divorce_family": ["family", "divorce", "marriage", "dower", "maintenance", "custody", "guardian", "dissolution", "wife", "husband", "spouse", "nikah"],
            "corporate_tax": ["tax", "corporate", "company", "income", "banking", "finance", "secp", "shares", "agreement", "contract", "business"],
            "government_constitutional": ["constitution", "writ", "petition", "fundamental", "rights", "authority", "government", "officer", "service", "civil", "public"]
        }
        
        for m in prioritized_matches:
            meta = {}
            if isinstance(m, dict):
                meta = m.get("metadata", {}) or {}
            elif hasattr(m, "metadata"):
                meta = getattr(m, "metadata", {}) or {}
            
            # Enforce Relevance Threshold of 0.70
            score = float(m.get("score", 0.0) if isinstance(m, dict) else getattr(m, "score", 0.0))
            if score < 0.70:
                continue

            # Skip Qurban Ali unverified chunk
            chunk_id = str(m.get("id", ""))
            case_id_val = str(meta.get("case_id", ""))
            if "2026L3032" in chunk_id or "2026L3032" in case_id_val:
                continue

            # Skip if explicitly marked unverified
            if meta.get("unverified") is True:
                continue
                
            # Deduplicate check (by case_id and citation)
            cid = meta.get("case_id")
            cit = meta.get("citation")
            if cid and cid in seen_case_ids:
                continue
            if cit and cit in seen_citations:
                continue
                
            # Generous Category Filtering
            if cat_lower != "general" and cat_lower in category_keywords:
                citation = str(meta.get('citation', '')).lower()
                subject = str(meta.get('subject_matter', '')).lower()
                title = str(meta.get('title', '')).lower()
                text = str(meta.get('text', meta.get('text_preview', ''))).lower()
                
                combined_text = f"{citation} {subject} {title} {text}"
                
                # Check if it has any keywords matching the current category
                has_category_relevance = any(k in combined_text for k in category_keywords[cat_lower])
                
                # Check if it belongs exclusively to another category
                belongs_to_other_category = False
                for other_cat, keywords in category_keywords.items():
                    if other_cat != cat_lower:
                        if any(k in combined_text for k in keywords) and not has_category_relevance:
                            belongs_to_other_category = True
                            break
                
                # Filter out ONLY if it has zero relevance to the active category and belongs exclusively to another domain
                if belongs_to_other_category and not has_category_relevance:
                    print(f"Skipping out-of-category case: {meta.get('citation')} (Active category: {cat_lower})", file=sys.stderr)
                    continue

            if cid:
                seen_case_ids.add(cid)
            if cit:
                seen_citations.add(cit)
            filtered_matches.append(m)

        # Slice to the resolved_top_k limits (5 default, 3 for very long queries to optimize speed)
        resolved_top_k = 3 if len(request.query_text) > 3000 else 5
        sliced_matches = filtered_matches[:resolved_top_k]
        
        high_relevance_segments = []
        medium_relevance_segments = []
        low_relevance_segments = []

        for match in sliced_matches:
            meta = {}
            if isinstance(match, dict):
                meta = match.get("metadata", {}) or {}
            elif hasattr(match, "metadata"):
                meta = getattr(match, "metadata", {}) or {}
                
            if isinstance(meta, dict):
                court = str(meta.get('court', 'Unknown Court'))
                year = str(meta.get('year', 'Unknown Year'))
                case_id = str(meta.get('case_id', 'Unknown ID'))
                
                # Fetch full text from index first, fall back to preview if older ingest format
                text_content = str(meta.get('text', meta.get('text_preview', '')))
                title = str(meta.get('title', 'Untitled Case'))
                citation = str(meta.get('citation', 'No Citation'))
                
                # Clean title to prevent repeated names/phrases
                title = clean_repeated_phrases(title)

                # Resolve court and apply clean-up rules
                court_val = court
                if not court or court.strip().lower() in ("not specified", "unknown", "none", "pakistanlawsite"):
                    if citation and citation != "No Citation":
                        court_val = citation
                    elif title and title != "Untitled Case":
                        court_val = title
                    else:
                        court_val = "High Court"

                display_court = clean_court_name(court_val)

                segment_text = (
                    f"Source: {display_court} ({year}) | Citation: {citation} | Title: {title} | Ref: {case_id}\n"
                    f"Content: {text_content}"
                )
                
                match_score = float(match.get("score", 0.0) if isinstance(match, dict) else getattr(match, "score", 0.0))
                
                # Categorize into Relevance Tiers
                relevance_label = "Low"
                if match_score >= 0.80:
                    relevance_label = "High"
                    high_relevance_segments.append(segment_text)
                elif match_score >= 0.75:
                    relevance_label = "Medium"
                    medium_relevance_segments.append(segment_text)
                else:
                    low_relevance_segments.append(segment_text)

                citations_payload.append({
                    "case_id": case_id,
                    "court": display_court,
                    "year": year,
                    "preview": text_content[:400],
                    "title": title,
                    "citation": citation,
                    "score": match_score,
                    "relevance": relevance_label
                })
            
        # Build structured context by relevance level to direct the AI's citation hierarchy
        context_parts = []
        if high_relevance_segments:
            context_parts.append("=== HIGH RELEVANCE CASES (Score >= 0.80) ===\n" + "\n\n---\n\n".join(high_relevance_segments))
        if medium_relevance_segments:
            context_parts.append("=== MEDIUM RELEVANCE CASES (Score 0.75 - 0.80) ===\n" + "\n\n---\n\n".join(medium_relevance_segments))
        if low_relevance_segments:
            context_parts.append("=== LOW RELEVANCE CASES (Score 0.70 - 0.75) ===\n" + "\n\n---\n\n".join(low_relevance_segments))
            
        combined_context = "\n\n=========================================\n\n".join(context_parts)
        
        # 4. Format Prompt and Call Anthropic
        system_prompt = SYSTEM_PROMPTS.get(request.category, SYSTEM_PROMPTS["general"])
        
        # Append strict reliability and verification constraints (Bugs #1, #2, #3, #6, Formatting, Drafting)
        global_reliability_guard = (
            f"\n\n=== STRICT ACCURACY, CITATION & DRAFTING FORMAT RULES ===\n"
            f"1. Citation Format & Spacing: You must use the exact space-separated journal formatting rules (do NOT use arrows, dashes or other characters):\n"
            f"   - PLD [Year] [Court Abbreviation] [Page] (e.g., PLD 2019 SC 524)\n"
            f"   - [Year] SCMR [Page] (e.g., 2019 SCMR 524)\n"
            f"   - [Year] [MLD/YLR/PCrLJ] [Page] [Court] (e.g., 2014 MLD 342 Karachi, 2026 YLR 226 Karachi, 2025 PCrLJ 112 Lahore)\n"
            f"2. Inline Narrative Pattern: Citations must be placed inline, immediately after each legal point (never bunched at the end). For each ground/precedent, follow this 5-part cycle:\n"
            f"   - Part 1: Bolded thesis statement (single bolded paragraph bullet stating the legal proposition).\n"
            f"   - Part 2: Introductory sentence placing reliance: \"In this regard, reliance is [firstly/further/similarly] placed upon the judgment reported as **[Citation]**, wherein it was held:\"\n"
            f"   - Part 3: Block quotation of the judgment (verbatim, italicized, paragraph-numbered like `***7.***` with key phrases bolded).\n"
            f"   - Part 4: Annexure citation line: \"(*Copy of the Judgment reported as **[Citation]** is attached as **Annexure [Letter]***)\"\n"
            f"   - Part 5: Application paragraph (plain text connecting facts, ending in conclusory submission like '...rendering the Petitioner entitled to...').\n"
            f"3. Case Summary Placement & Format: For every case you cite, you must write a highly comprehensive, detailed 15-to-25 line summary (strictly no more than 25 lines) covering the case facts, authoring judge name, key findings, and ratio decidendi. If in 'drafting' mode, integrate this 15-to-25 line summary directly inline under the citation as part of the 5-part precedent block, rather than grouping them at the end of the response. If in any other answering mode, format it at the end of your response inside a clean markdown block with the header '### Case Summaries'.\n"
            f"4. Drafting Mode Format: If the user requests a draft (petition, plaint, bail application, etc.), you MUST follow the exact template in the system rules:\n"
            f"   - Start with Caption Block: IN THE HONOURABLE [COURT] HIGH COURT (bold, all caps, centered), WRIT PETITION NO. ___ / [YEAR] (bold), Petitioner/Respondents names italicized with right-aligned ellipsis and labels (e.g., '... Petitioner' / '… Respondents'), and 'Versus' centered and italicized.\n"
            f"   - PETITION UNDER ARTICLE [X] ... READ WITH ... (bold, all caps).\n"
            f"   - SUBMISSIONS ON BEHALF OF THE [PARTY] (bold, all caps).\n"
            f"   - Transition grounds using formal transitional connectors (e.g., 'Moreover', 'Furthermore', 'Much in a similar vein'). Do not use first person.\n"
            f"5. Citing Holdings (Precedent Gate): Before asserting a specific holding, ratio decidendi, or rule from a cited case precedent, "
            f"you MUST verify that the holding is explicitly detailed in the provided Context from Legal Database. "
            f"If the Context does not explicitly confirm that specific holding, you must hedge using this exact phrase: "
            f"\"A case of this name and citation exists in Pakistani jurisprudence on a related subject, but I cannot confirm this specific holding without further verification.\"\n"
            f"6. Unindexed Statutes: The Companies Act 2017 is currently unindexed in the vector database. "
            f"If you generate any section or article number for the Companies Act 2017 (or other statutes not present in the Context), "
            f"you MUST flag it by appending: \"(Note: Section number reconstructed from general knowledge, not retrieved from indexed text — confirm against the Gazette text before filing.)\"\n"
            f"7. Complete Statutory Quotes: When citing or quoting statutory sections (such as Section 50 of the Registration Act 1908 or any other section), "
            f"you MUST include the complete section and its relevant provisos (e.g., references to Section 53-A of the Transfer of Property Act or Section 27(b) of the Specific Relief Act) "
            f"rather than quoting only the lead subsection, to ensure a complete and accurate legal representation.\n"
            f"8. Superseded Narcotics Statutes (CNSA 1997): The Control of Narcotic Substances Act 1997 was significantly amended in 2022 and 2023, restructuring the Section 9 quantity-based sentencing thresholds. "
            f"Whenever you cite CNSA 1997 sentencing thresholds or quantities, you MUST state the 1997 limits but explicitly add: \"(Note: Sentencing thresholds and quantity tiers have changed under the 2022/2023 CNSA Amendments. Verify against the latest official Gazette text before filing.)\"\n"
            f"9. Prohibition on External Case Citations: Do NOT introduce, invent, or reference any specific case names, citation numbers, or precedents from your own general knowledge (such as Abdul Kareem, Jurial Shah, or others) unless they are explicitly present in the provided 'Context from Legal Database'. This rule applies strictly to all follow-up responses and turns. Do not introduce new case names or citations in subsequent answers unless they are explicitly part of the retrieved context block for that turn. If you need to refer to a general legal concept or strategy, describe it conceptually without citing unverified external cases.\n"
            f"10. Category Discipline & Contextual Relevance: The user is querying under the active category '{request.category}'. "
            f"Prioritize legal principles, acts, and procedural rules relevant to this category. "
            f"If the provided database context contains cases from other legal domains (e.g., a family dispute case retrieved during a criminal query), "
            f"you must either ignore it or explicitly distinguish it in your response. Do not cite out-of-category precedents as substantive authorities "
            f"unless they lay down a general procedural rule that directly applies to the matter.\n"
            f"11. Precedent Citation Hierarchy: The retrieved legal context blocks are separated by relevance: HIGH RELEVANCE (most relevant), MEDIUM RELEVANCE, and LOW RELEVANCE. "
            f"When citing precedents to support your arguments or drafts, you MUST strictly follow this sequence: always cite the most relevant (HIGH RELEVANCE) cases first. If a legal point cannot be supported by any HIGH RELEVANCE cases, only then move/fallback to MEDIUM RELEVANCE cases. If the legal point is still not supported, only then move/fallback to LOW RELEVANCE cases. Do not reference lower relevance tiers if a higher relevance tier can support the legal point."
        )
        system_prompt += global_reliability_guard
        system_prompt += f"\n\n=== EXPLICIT ROUTING INSTRUCTION ===\nActive Mode: The AI is operating in '{mode.upper()}' mode. Adapt your writing register, style, and detail level to match this mode.\n"
        if mode == "drafting":
            system_prompt += "Drafting Instruction: Since the user is requesting a legal draft, you MUST strictly format the document using the caption structures and repeating 5-part grounds/narrative cycles defined in the Constitutional Writ template in Section 4.\n"
        
        # 5. Build final messages payload
        claude_message_content = []
        if has_image:
            # Add all image blocks to the final payload
            for img in images_list:
                claude_message_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": sanitize_mime_type(img.image_mime_type),
                        "data": clean_base64_data(img.image_base64)
                    }
                })
            
            # Instruct Claude to perform full OCR, translation, and answer in one pass
            prompt_text = (
                f"Context from Legal Database:\n{combined_context}\n\n"
                "Please analyze the attached legal document page(s) and the reference database context to answer the query.\n"
                "First, perform the following transcription and translation tasks:\n"
                "1. Transcribe the full text from the attached images accurately. If the text is in Urdu (Nastaliq script), transcribe it using Urdu script, and English text in English.\n"
                "2. If the text contains Urdu, provide a high-quality, complete English translation right below the transcription.\n\n"
                f"Question: {request.query_text}"
            )
            claude_message_content.append({
                "type": "text",
                "text": prompt_text
            })
        else:
            claude_message_content = f"Context from Legal Database:\n{combined_context}\n\nQuestion: {request.query_text}"

        print(f"🧠 [JOB {job_id}] Attempting connection to Anthropic Claude API...", file=sys.stderr, flush=True)
        main_input_tokens = 0
        main_output_tokens = 0
        if async_anthropic_client and ANTHROPIC_API_KEY:
            final_kwargs = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 4000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": claude_message_content}]
            }
            if os.environ.get("LANGCHAIN_API_KEY"):
                final_kwargs["langsmith_extra"] = {
                    "metadata": {
                        "user_id": authenticated_user_id,
                        "job_id": job_id,
                        "category": request.category,
                        "task": "final_legal_evaluation"
                    }
                }
            claude_message = await async_anthropic_client.messages.create(**final_kwargs)
            
            if hasattr(claude_message, "usage") and claude_message.usage:
                main_input_tokens = getattr(claude_message.usage, "input_tokens", 0) or 0
                main_output_tokens = getattr(claude_message.usage, "output_tokens", 0) or 0
            
            generated_answer = ""
            for block in claude_message.content:
                block_text = getattr(block, "text", "")
                if block_text:
                    generated_answer += block_text
        else:
            generated_answer = f"### Legal Evaluation (Simulation mode - Category: {request.category})\n\nPrecedent found: **{citations_payload[0]['case_id'] if citations_payload else 'N/A'}**."
        
        # Aggregate total tokens
        input_tokens = main_input_tokens + vision_input_tokens
        output_tokens = main_output_tokens + vision_output_tokens

        # 5. Log and Save
        print(f"💾 [JOB {job_id}] Inserting query logging data into Supabase...", file=sys.stderr, flush=True)
        inserted_row_id = str(uuid.uuid4())
        if supabase:
            db_insert = supabase.table("queries").insert({
                "user_id": authenticated_user_id,
                "query_text": f"[Vision Context] {request.query_text}" if has_image else request.query_text,
                "answer_text": generated_answer,
                "citations": citations_payload,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }).execute()
            
            if db_insert.data and len(db_insert.data) > 0:
                first_insert = db_insert.data[0]
                if isinstance(first_insert, dict):
                    inserted_row_id = str(first_insert.get("id", inserted_row_id))
        else:
            print(f"⚠️ [JOB {job_id}] Skipped logging query to database (Supabase client offline)")
                
        print(f"✅ [JOB {job_id}] Query lifecycle resolved successfully!", file=sys.stderr, flush=True)
        
        # Save to jobs store
        if job_id in jobs_store:
            jobs_store[job_id].update({
                "status": "done",
                "result": {"answer": generated_answer, "citations": citations_payload, "query_id": inserted_row_id, "mode": mode},
                "completed_at": datetime.now(timezone.utc)
            })

    except Exception as e:
        import traceback
        print(f"❌ [CRITICAL ENGINE CRASH INSIDE JOB {job_id}]:", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        
        if os.environ.get("SENTRY_DSN"): 
            sentry_sdk.capture_exception(e)
            
        if job_id in jobs_store:
            jobs_store[job_id].update({
                "status": "error",
                "error": str(e),
                "completed_at": datetime.now(timezone.utc)
            })

@app.post("/query")
async def execute_legal_query(
    request: QueryRequest, 
    background_tasks: BackgroundTasks,
    authenticated_user_id: str = Depends(verify_clerk_session)
):
    from datetime import datetime, timezone
    cleanup_old_jobs()
    
    # 1. Quick initial quota check to fail fast before queueing the task
    images_list = request.images or []
    num_images = len(images_list)
    try:
        check_user_quota(authenticated_user_id, num_images_requested=num_images)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    job_id = str(uuid.uuid4())
    jobs_store[job_id] = {
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "user_id": authenticated_user_id
    }
    
    background_tasks.add_task(process_query_job, job_id, request, authenticated_user_id)
    return {"job_id": job_id}

@app.get("/query/{job_id}")
async def get_query_job_status(job_id: str, authenticated_user_id: str = Depends(verify_clerk_session)):
    cleanup_old_jobs()
    
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = jobs_store[job_id]
    if job["user_id"] != authenticated_user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job.")
        
    response = {
        "status": job["status"]
    }
    if job["status"] == "done":
        response["result"] = job.get("result")
    elif job["status"] == "error":
        response["error"] = job.get("error")
        
    return response

@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest, authenticated_user_id: str = Depends(verify_clerk_session)):
    """
    📝 FEEDBACK LOGGER GATEWAY: Records corrections and user remarks into the 
    Supabase relational training ledger for offline fine-tuning pipelines.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database service is currently offline.")
    try:
        res = supabase.table("feedback").insert({
            "query_id": request.query_id,
            "original_answer": request.original_answer,
            "correct_answer": request.correct_answer,
            "user_id": authenticated_user_id
        }).execute()
        return {"status": "success", "message": "Feedback submitted successfully.", "data": res.data}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------------------------
# Dynamic Onboarding & User Profile Customizations (New Contracts)
# ----------------------------------------------------------------------
@app.post("/users/update-profile")
async def update_user_profile(payload: ProfileUpdatePayload, authenticated_user_id: str = Depends(verify_clerk_session)):
    """
    🖋️ USER PROFILE UPDATE GATE: Accepts name metadata from Lovable onboarding elements
    and updates the master relational users profile index using active Clerk identity credentials.
    """
    try:
        res = supabase.table("users").update({
            "full_name": payload.full_name
        }).eq("id", authenticated_user_id).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="User database profile row not found.")
        return {"status": "success", "user": res.data[0]}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to update onboarding user name layout parameters: {str(e)}")

# ----------------------------------------------------------------------
# Administrative System Configurations & User Management (New Contracts)
# ----------------------------------------------------------------------
# Helper to normalize frontend date picker formats (e.g. DD/MM/YYYY) to PostgreSQL ISO format
def parse_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        # Check DD/MM/YYYY format
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str.strip())
        if match:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    except Exception:
        pass
    return date_str

# ----------------------------------------------------------------------
# Administrative System Configurations & User Management (New Contracts)
# ----------------------------------------------------------------------
@app.get("/admin/associates")
async def list_associates(admin_id: str = Depends(verify_admin_role)):
    """
    👥 ADMIN ASSOCIATE COMPILATION LIST: Compiles a data roster of all registered
    users active inside the infrastructure database, adding query counts and last active timestamps.
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database service is offline.")
    try:
        # 1. Fetch all users
        res = supabase.table("users").select("*").order("full_name").execute()
        users_list = res.data if res else []
        
        # 2. Fetch query metrics to calculate total queries and last active times
        queries_res = supabase.table("queries").select("user_id", "created_at").execute()
        queries_list = queries_res.data if queries_res else []
        
        user_stats = {}
        for q in queries_list:
            if not isinstance(q, dict):
                continue
            uid = q.get("user_id")
            if not uid:
                continue
            if uid not in user_stats:
                user_stats[uid] = {
                    "total_queries": 0,
                    "last_active_at": None
                }
            user_stats[uid]["total_queries"] += 1
            
            created_str = q.get("created_at")
            if created_str:
                if not user_stats[uid]["last_active_at"] or created_str > user_stats[uid]["last_active_at"]:
                    user_stats[uid]["last_active_at"] = created_str
                    
        # 3. Join stats into users list
        for user in users_list:
            if not isinstance(user, dict):
                continue
            uid = user.get("id")
            stats = user_stats.get(uid, {"total_queries": 0, "last_active_at": None})
            user["total_queries"] = stats["total_queries"]
            user["last_active_at"] = stats["last_active_at"]
            user["last_active"] = stats["last_active_at"] # Fallback key
            
        return users_list
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to list system associates: {str(e)}")

@app.post("/admin/associates")
async def create_associate(payload: AssociateCreatePayload, admin_id: str = Depends(verify_admin_role)):
    """
    ➕ ADMIN PRE-APPROVAL HANDSHAKE: Injects a pre-approved invitation request straight
    into the access table, setting up seamless pass-through registration tracking.
    """
    try:
        duplicate_check = supabase.table("access_requests").select("id").eq("email", payload.email).execute()
        if duplicate_check.data and len(duplicate_check.data) > 0:
            res = supabase.table("access_requests").update({
                "full_name": payload.full_name,
                "status": payload.status
            }).eq("email", payload.email).execute()
        else:
            res = supabase.table("access_requests").insert({
                "full_name": payload.full_name,
                "email": payload.email,
                "firm_name": "Pre-Approved Associate Firm",
                "status": payload.status
            }).execute()
            
        return {"status": "success", "message": "Associate email invitation pre-approved successfully.", "data": res.data}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to provision associate registration workspace allowance: {str(e)}")

@app.post("/admin/associates/{associate_id}/status")
async def set_associate_status(associate_id: str, payload: AssociateStatusPayload, admin_id: str = Depends(verify_admin_role)):
    """
    🔄 ADMIN PRIVILEGE CONTROLLER: Dynamically updates structural authorization parameters
    or user workspace execution permissions straight from the master user table grid.
    """
    try:
        res = supabase.table("users").update({
            "role": payload.status
        }).eq("id", associate_id).execute()
        
        if not res.data or len(res.data) == 0:
            raise HTTPException(status_code=404, detail="Target associate user profile row was not discovered.")
        return {"status": "success", "data": res.data[0]}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to adjust associate clearance matrix parameters: {str(e)}")

@app.delete("/admin/associates/{associate_id}")
async def delete_associate(associate_id: str, admin_id: str = Depends(verify_admin_role)):
    """
    ❌ ADMIN SYSTEM EXPULSION: Wipes out profile mappings for an un-linked or terminated associate
    completely across administrative database control blocks.
    """
    try:
        supabase.table("users").delete().eq("id", associate_id).execute()
        return {"status": "success", "message": f"Associate footprint '{associate_id}' purged cleanly from core memory fields."}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to eliminate target associate entry frame: {str(e)}")

@app.get("/admin/activity")
async def list_all_activity(
    request: Request,
    associate_id: Optional[str] = None, 
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None, 
    admin_id: str = Depends(verify_admin_role)
):
    """
    📊 GLOBAL AUDIT LOG LOGGER: Streams query activity logs from the queries table,
    joining user details for clear administrator overview. Supports date filters.
    """
    if not supabase:
        return []
    try:
        # Extract from and to parameters if sent by frontend as aliases
        from_val = from_date or request.query_params.get("from")
        to_val = to_date or request.query_params.get("to")
        
        query = supabase.table("queries").select("*")
        if associate_id:
            query = query.eq("user_id", associate_id)
        
        parsed_from = parse_date_to_iso(from_val)
        parsed_to = parse_date_to_iso(to_val)
        
        if parsed_from:
            query = query.gte("created_at", parsed_from)
        if parsed_to:
            query = query.lte("created_at", parsed_to)
            
        res = query.order("created_at", desc=True).limit(500).execute()
        raw_data = res.data if res else []
        
        # Fetch users to map user_id -> name/email safely in Python memory
        users_res = supabase.table("users").select("id", "full_name", "email").execute()
        users_map = {u["id"]: u for u in users_res.data} if users_res and users_res.data else {}
        
        formatted_activity = []
        for r in raw_data:
            if not isinstance(r, dict):
                continue
            uid = r.get("user_id")
            user_info = users_map.get(uid, {})
            full_name = user_info.get("full_name") or user_info.get("email") or "Unknown Associate"
            q_text = r.get("query_text", "")
            ans_text = r.get("answer_text", "")
            
            # Determine type of query activity
            is_vision = q_text and "[Vision Context]" in str(q_text)
            action_type = "Vision Query" if is_vision else "Text Query"
            clean_question = str(q_text).replace("[Vision Context] ", "") if q_text else ""
            
            formatted_activity.append({
                "id": r.get("id"),
                "user_id": uid,
                "associate": full_name,
                "full_name": full_name,
                "email": user_info.get("email"),
                "created_at": r.get("created_at"),
                "time": r.get("created_at"),
                "type": action_type,
                "action_type": action_type,
                "question": clean_question,
                "description": clean_question,
                "response": ans_text,
                "answer_text": ans_text,
                "result": ans_text,
                "answer": ans_text
            })
            
        return formatted_activity
    except Exception as e:
        print(f"⚠️ Activity Log Stream Warning: {str(e)}")
        return []

@app.get("/admin/associates/usage")
async def list_associates_usage(
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None, 
    admin_id: str = Depends(verify_admin_role)
):
    """
    📊 ADMIN USAGE DASHBOARD: Fetches usage statistics (queries, vision uploads, tokens)
    for all registered users. Supports custom date filters (defaults to last 24 hours).
    """
    if not supabase:
        raise HTTPException(status_code=503, detail="Database service is offline.")
    try:
        from datetime import datetime, timezone, timedelta
        
        # 1. Fetch all users
        users_res = supabase.table("users").select("id", "email", "full_name", "role").order("full_name").execute()
        users_list = users_res.data if users_res else []
        
        # 2. Build queries call
        query = supabase.table("queries").select("user_id", "query_text", "input_tokens", "output_tokens")
        
        parsed_from = parse_date_to_iso(from_date)
        parsed_to = parse_date_to_iso(to_date)
        
        if parsed_from:
            query = query.gte("created_at", parsed_from)
        if parsed_to:
            query = query.lte("created_at", parsed_to)
            
        # Default to last 24h if no date filter is provided
        if not parsed_from and not parsed_to:
            time_limit = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            query = query.gte("created_at", time_limit)
            
        queries_res = query.execute()
        queries_list = queries_res.data if queries_res else []
        
        # 3. Aggregate metrics by user_id
        user_metrics = {}
        for q in queries_list:
            if not isinstance(q, dict):
                continue
            uid = q.get("user_id")
            if not uid:
                continue
            if uid not in user_metrics:
                user_metrics[uid] = {
                    "text_queries_used": 0,
                    "vision_queries_used": 0,
                    "input_tokens_used": 0,
                    "output_tokens_used": 0
                }
            
            user_metrics[uid]["text_queries_used"] += 1
            
            q_text = q.get("query_text", "")
            if q_text and "[Vision Context]" in str(q_text):
                user_metrics[uid]["vision_queries_used"] += 1
                
            user_metrics[uid]["input_tokens_used"] += int(q.get("input_tokens") or 0)
            user_metrics[uid]["output_tokens_used"] += int(q.get("output_tokens") or 0)
            
        # 4. Map back to users list
        response_data = []
        for user in users_list:
            if not isinstance(user, dict):
                continue
            uid = user.get("id")
            metrics = user_metrics.get(uid, {
                "text_queries_used": 0,
                "vision_queries_used": 0,
                "input_tokens_used": 0,
                "output_tokens_used": 0
            })
            
            response_data.append({
                "id": uid,
                "email": user.get("email"),
                "full_name": user.get("full_name"),
                "role": user.get("role"),
                "usage": {
                    "text_queries_used": metrics["text_queries_used"],
                    "text_queries_limit": 100,
                    "vision_queries_used": metrics["vision_queries_used"],
                    "vision_queries_limit": 30,
                    "input_tokens_used": metrics["input_tokens_used"],
                    "output_tokens_used": metrics["output_tokens_used"],
                    "total_tokens_used": metrics["input_tokens_used"] + metrics["output_tokens_used"]
                }
            })
            
        return response_data
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to compile users usage status: {str(e)}")

@app.get("/admin/export-training-data")
async def export_training_data(admin_id: str = Depends(verify_admin_role)):
    try:
        feedback_res = supabase.table("feedback").select("*").execute()
        feedback_records = feedback_res.data if feedback_res else []
        if not feedback_records:
            return {"message": "Dataset compilation complete: 0 correction records found.", "jsonl_payload": []}
            
        jsonl_dataset = []
        for item in feedback_records:
            if not isinstance(item, dict):
                continue
                
            q_id = item.get("query_id")
            if not q_id:
                continue
                
            q_res = supabase.table("queries").select("query_text").eq("id", q_id).execute()
            if q_res.data and len(q_res.data) > 0:
                first_q = q_res.data[0]
                if isinstance(first_q, dict):
                    query_text = first_q.get("query_text", "")
                    correct_answer = item.get("correct_answer", "")
                    
                    training_line = {
                        "messages": [
                            {"role": "user", "content": str(query_text)},
                            {"role": "assistant", "content": str(correct_answer)}
                        ]
                    }
                    jsonl_dataset.append(training_line)
                
        return {"total_training_records": len(jsonl_dataset), "jsonl_payload": jsonl_dataset}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))