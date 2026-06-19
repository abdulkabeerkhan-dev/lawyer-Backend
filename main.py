import os
import uuid
from fastapi import FastAPI, HTTPException, status, Depends
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

# 🔒 SECURITY ACCESS CORE: Cross-Origin Resource Sharing gateway adjustments
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Production Environment Variable Guard Checks
# ----------------------------------------------------------------------
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not PINECONE_API_KEY:
    raise RuntimeError("CRITICAL LAUNCH ERROR: 'PINECONE_API_KEY' environment variable is missing!")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError("CRITICAL LAUNCH ERROR: Supabase database connection tokens are missing!")

# Initialize Production Cloud Infrastructures securely
pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Initialize Anthropic Client conditionally to support fallback simulations
async_anthropic_client = None
if ANTHROPIC_API_KEY:
    async_anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
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

    # Local fallback bypass for isolated testing environments
    if os.environ.get("FRONTEND_URL", "*") == "*":
        return "mock_clerk_user_id_dev_run"
        
    clerk_secret = os.environ.get("CLERK_SECRET_KEY")
    if not clerk_secret:
        print("❌ [AUTH MONITOR] Deployment Error: CLERK_SECRET_KEY variable missing inside parameters.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration missing: 'CLERK_SECRET_KEY' environment variable is not defined."
        )
        
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

class QueryRequest(BaseModel):
    query_text: str

class FeedbackRequest(BaseModel):
    query_id: str
    original_answer: str
    correct_answer: str

# ----------------------------------------------------------------------
# Core Operation Controllers (Existing Workflows)
# ----------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/request-access")
async def register_access_request(request: AccessRegistration):
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
    try:
        profile_query = supabase.table("users").select("*").eq("id", authenticated_user_id).execute()
        if profile_query.data and len(profile_query.data) > 0:
            return {"status": "exists", "user": profile_query.data[0]}
            
        access_check = supabase.table("access_requests").select("status").eq("email", payload.email).execute()
        assigned_role = "associate"
        if access_check.data and len(access_check.data) > 0:
            first_access = access_check.data[0]
            if isinstance(first_access, dict) and first_access.get("status") == "admin_approved":
                assigned_role = "admin"

        inserted_profile = supabase.table("users").insert({
            "id": authenticated_user_id,
            "email": payload.email,
            "full_name": payload.full_name,
            "role": assigned_role
        }).execute()
        return {"status": "created", "user": inserted_profile.data[0]}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query")
async def execute_legal_query(request: QueryRequest, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        bge_query_text = f"Represent this sentence for searching relevant passages: {request.query_text}"
        hf_api_url = "https://api-inference.huggingface.co/pipeline/feature-extraction/BAAI/bge-large-en-v1.5"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            hf_response = await client.post(hf_api_url, json={"inputs": bge_query_text})
            if hf_response.status_code != 200:
                raise HTTPException(status_code=502, detail="Hugging Face Inference Engine failure.")
            query_vector = hf_response.json()

        raw_matches = pinecone_index.query(namespace="judgments", vector=query_vector, top_k=8, include_metadata=True)
        context_segments = []
        citations_payload = []
        
        matches_list = []
        if isinstance(raw_matches, dict):
            matches_list = raw_matches.get("matches", [])
        elif hasattr(raw_matches, "matches"):
            matches_list = getattr(raw_matches, "matches", []) or []
        
        for match in matches_list:
            meta = {}
            if isinstance(match, dict):
                meta = match.get("metadata", {}) or {}
            elif hasattr(match, "metadata"):
                meta = getattr(match, "metadata", {}) or {}
                
            if isinstance(meta, dict):
                court = str(meta.get('court', 'Unknown Court'))
                year = str(meta.get('year', 'Unknown Year'))
                case_id = str(meta.get('case_id', 'Unknown ID'))
                text_preview = str(meta.get('text_preview', ''))
                
                context_segments.append(f"Source: {court} ({year}) | Ref: {case_id}\nContent: {text_preview}")
                citations_payload.append({"case_id": case_id, "court": court, "year": year, "preview": text_preview})
            
        combined_context = "\n\n---\n\n".join(context_segments)
        
        if async_anthropic_client and ANTHROPIC_API_KEY:
            system_prompt = "You are an elite, highly precise Pakistani legal expert. Answer strictly based on the context data blocks provided, citing explicitly."
            claude_message = await async_anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2500,
                system=system_prompt,
                messages=[{"role": "user", "content": f"Context:\n{combined_context}\n\nQuestion: {request.query_text}"}]
            )
            
            # Using safe attribute unpacking loops to keep Pylance from flagging alternative thinking blocks
            generated_answer = ""
            for block in claude_message.content:
                block_text = getattr(block, "text", "")
                if block_text:
                    generated_answer += block_text
        else:
            generated_answer = f"### Legal Evaluation (Simulation mode)\n\nPrecedent found: **{citations_payload[0]['case_id'] if citations_payload else 'N/A'}**."
        
        db_insert = supabase.table("queries").insert({
            "user_id": authenticated_user_id,
            "query_text": request.query_text,
            "answer_text": generated_answer,
            "citations": citations_payload
        }).execute()
        
        inserted_row_id = str(uuid.uuid4())
        if db_insert.data and len(db_insert.data) > 0:
            first_insert = db_insert.data[0]
            if isinstance(first_insert, dict):
                inserted_row_id = str(first_insert.get("id", inserted_row_id))
                
        return {"answer": generated_answer, "citations": citations_payload, "query_id": inserted_row_id}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        supabase.table("feedback").insert({
            "query_id": request.query_id,
            "user_id": authenticated_user_id,
            "original_answer": request.original_answer,
            "correct_answer": request.correct_answer
        }).execute()
        return {"status": "feedback saved"}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"): sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{user_id}")
async def get_user_history(user_id: str, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        if user_id != authenticated_user_id and authenticated_user_id != "mock_clerk_user_id_dev_run":
            raise HTTPException(status_code=403, detail="Profile reference mismatch.")
        res = supabase.table("queries").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return res.data
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
@app.get("/admin/associates")
async def list_associates(admin_id: str = Depends(verify_admin_role)):
    """
    👥 ADMIN ASSOCIATE COMPILATION LIST: Compiles a data roster of all registered
    users active inside the infrastructure database for admin viewing dashboards.
    """
    try:
        res = supabase.table("users").select("*").order("full_name").execute()
        return res.data
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
    associate_id: Optional[str] = None, 
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None, 
    admin_id: str = Depends(verify_admin_role)
):
    """
    📊 GLOBAL AUDIT LOG LOGGER: Streams comprehensive tracking elements from centralized activity fields,
    allowing advanced sorting by individual associate identities or historical timeframes.
    """
    try:
        query = supabase.table("activity_log").select("*")
        if associate_id:
            query = query.eq("user_id", associate_id)
        if from_date:
            query = query.gte("created_at", from_date)
        if to_date:
            query = query.lte("created_at", to_date)
            
        res = query.order("created_at", desc=True).execute()
        return res.data
    except Exception as e:

# 👇 ADD THESE TWO LINES TO EXPOSE THE ERROR IN RAILWAY LOGS
        import traceback
        print("❌ [CRITICAL ENGINE CRASH INSIDE /QUERY]:")
        traceback.print_exc() 
        
        if os.environ.get("SENTRY_DSN"): 
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))


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