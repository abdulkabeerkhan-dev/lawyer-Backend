import os
import uuid
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, cast
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

app = FastAPI(title="TO BE NAMED AI LAWYER - Production Serverless Clerk-Secure Engine")

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

# Initialize Identity Token Extractor Agent
security_agent = HTTPBearer()

# Global cache memory to keep token authorization verification ultra-fast without repeating network roundtrips
_clerk_jwks_keys_cache = None

async def verify_clerk_session(credentials: HTTPAuthorizationCredentials = Depends(security_agent)) -> str:
    """
    🔐 DYNAMIC CLERK PRODUCTION BOUNDARY: Extracts the incoming bearer token,
    authenticates signatures against Clerk's official secure JWKS public key cache layer,
    and returns the unique verified User ID string ('sub').
    """
    global _clerk_jwks_keys_cache
    token = credentials.credentials
    
    # 🔍 SYSTEM DIAGNOSTIC PRINT: Instantly verifies what the backend is receiving
    print(f"🔑 [AUTH MONITOR] Token Length: {len(token) if token else 0} | Content Snippet: {str(token)[:20]}...")

    # Local fallback bypass for isolated local testing environments
    if os.environ.get("FRONTEND_URL", "*") == "*":
        return "mock_clerk_user_id_dev_run"
        
    clerk_secret = os.environ.get("CLERK_SECRET_KEY")
    if not clerk_secret:
        print("❌ [AUTH MONITOR] Deployment Error: CLERK_SECRET_KEY variable missing inside Railway parameters.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration missing: 'CLERK_SECRET_KEY' environment variable is not defined on the host."
        )
        
    try:
        # Extract the Key ID ('kid') header element from the token unverified
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            print("❌ [AUTH MONITOR] Validation Failed: The incoming token header is missing a Key ID ('kid').")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature architecture layout.")
            
        # Sync verified signature sets from Clerk keyservers if our RAM cache container is clear
        if not _clerk_jwks_keys_cache:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {clerk_secret}"}
                jwks_response = await client.get("https://api.clerk.com/v1/jwks", headers=headers)
                if jwks_response.status_code != 200:
                    print(f"❌ [AUTH MONITOR] Keyserver Error: Clerk rejected handshake with code {jwks_response.status_code}")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Failed to sync active authorization signature pairs from Clerk keyserver clusters."
                    )
                _clerk_jwks_keys_cache = jwks_response.json().get("keys", [])
                
        # Locate the public key structure matching the token signature reference
        public_key = None
        for key_data in _clerk_jwks_keys_cache:
            if key_data.get("kid") == kid:
                public_key = RSAAlgorithm.from_jwk(key_data)
                break
                
        if not public_key:
            print("❌ [AUTH MONITOR] Validation Failed: The token 'kid' does not match any cached Clerk signature keys.")
            _clerk_jwks_keys_cache = None  # Flush cache to force re-fetch on next query run
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Stale authentication signature validation parameters.")
            
        # 🛡️ DECODE WITH LEEWAY: Uses a 60-second time buffer to completely absorb server clock-skews
        decoded_payload = jwt.decode(
            token,
            key=cast(Any, public_key),
            algorithms=["RS256"],
            options={"verify_aud": False},
            leeway=60
        )
        
        user_id = decoded_payload.get("sub")
        if not user_id:
            print("❌ [AUTH MONITOR] Validation Failed: Token parsed successfully but lacks a subject ('sub') field.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile subject reference claim is missing from session payload.")
            
        print(f"✅ [AUTH MONITOR] Access Granted: User {user_id} successfully authenticated.")
        return str(user_id)
        
    except jwt.exceptions.ExpiredSignatureError as e:
        print(f"❌ [AUTH MONITOR] Cryptographic Denial: Token is expired. Details: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed: The provided session token has expired.")
    except Exception as error_context:
        print(f"❌ [AUTH MONITOR] Cryptographic Denial: Core verification dropped. Context: {str(error_context)}")
        raise HTTPException(status_code=401, detail=f"Access Denied: Token signature verification dropped: {str(error_context)}")

# ----------------------------------------------------------------------
# Data Transport Verification Forms (Pydantic Models)
# ----------------------------------------------------------------------
class UserSyncPayload(BaseModel):
    email: str
    full_name: str

class AccessRegistration(BaseModel):
    full_name: str
    firm_name: str
    email: str

class QueryRequest(BaseModel):
    query_text: str

class FeedbackRequest(BaseModel):
    query_id: str
    original_answer: str
    correct_answer: str

# ----------------------------------------------------------------------
# Operation Controller Endpoints
# ----------------------------------------------------------------------
@app.get("/health")
def health_check():
    """Used by Railway lifecycle observers to verify cluster fitness status."""
    return {"status": "healthy"}

@app.post("/request-access")
async def register_access_request(request: AccessRegistration):
    """
    🔓 PUBLIC ACCESS ENTRY POINT: Captures incoming waitlist configurations
    and saves requests securely inside the Supabase waitlist engine without auth constraints.
    """
    try:
        duplicate_check = supabase.table("access_requests").select("id").eq("email", request.email).execute()
        if duplicate_check.data and len(duplicate_check.data) > 0:
            return {
                "status": "duplicate", 
                "message": "Thank you! An invitation request for this email address is already under review."
            }
            
        supabase.table("access_requests").insert({
            "full_name": request.full_name,
            "firm_name": request.firm_name,
            "email": request.email,
            "status": "pending"
        }).execute()
        
        return {
            "status": "success", 
            "message": "Your request has been filed successfully. The team will review your credentials shortly."
        }
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Waitlist filing failed: {str(e)}")

@app.post("/users/sync")
async def sync_clerk_user_profile(payload: UserSyncPayload, authenticated_user_id: str = Depends(verify_clerk_session)):
    """
    🔐 PROTECTED PROFILE SYNC: Intercepts authenticated user entries,
    and initializes their relational database profile maps inside your Supabase users tracking grid.
    """
    try:
        profile_query = supabase.table("users").select("*").eq("id", authenticated_user_id).execute()
        
        if profile_query.data and len(profile_query.data) > 0:
            return {
                "status": "exists",
                "user": profile_query.data[0]
            }
            
        access_check = supabase.table("access_requests").select("status").eq("email", payload.email).execute()
        assigned_role = "associate"
        
        if access_check.data and len(access_check.data) > 0:
            first_row = access_check.data[0]
            if isinstance(first_row, dict) and first_row.get("status") == "admin_approved":
                assigned_role = "admin"

        inserted_profile = supabase.table("users").insert({
            "id": authenticated_user_id,
            "email": payload.email,
            "full_name": payload.full_name,
            "role": assigned_role
        }).execute()
        
        if not inserted_profile.data:
            raise HTTPException(status_code=500, detail="Database write confirmed but profile generation failed.")
            
        return {
            "status": "created",
            "user": inserted_profile.data[0]
        }
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"User profile synchronization failed: {str(e)}")

@app.post("/query")
async def execute_legal_query(request: QueryRequest, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        # 1. Compute incoming search coordinates via Hugging Face Serverless Inference API
        bge_query_text = f"Represent this sentence for searching relevant passages: {request.query_text}"
        hf_api_url = "https://api-inference.huggingface.co/pipeline/feature-extraction/BAAI/bge-large-en-v1.5"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            hf_response = await client.post(hf_api_url, json={"inputs": bge_query_text})
            if hf_response.status_code != 200:
                raise HTTPException(
                    status_code=502, 
                    detail=f"Hugging Face Inference Engine returned an unexpected status block: {hf_response.text}"
                )
            query_vector = hf_response.json()

        # 2. Query matching records from the standard 1024-dimensional index deployment
        raw_matches = pinecone_index.query(
            namespace="judgments",
            vector=query_vector,
            top_k=8,
            include_metadata=True
        )
        
        context_segments = []
        citations_payload = []
        matches_list = getattr(raw_matches, "matches", []) if not isinstance(raw_matches, dict) else raw_matches.get("matches", [])
        
        for match in matches_list:
            meta = getattr(match, "metadata", {}) if not isinstance(match, dict) else match.get("metadata", {})
            if not meta:
                meta = {}
            context_segments.append(
                f"Source: {meta.get('court')} ({meta.get('year')}) | Identification Reference: {meta.get('case_id')}\nContent Data: {meta.get('text_preview')}"
            )
            citations_payload.append({
                "case_id": meta.get("case_id"),
                "court": meta.get("court"),
                "year": meta.get("year"),
                "preview": meta.get("text_preview")
            })
            
        combined_context = "\n\n---\n\n".join(context_segments)
        
        # 3. Handle LLM Generation or Simulation Layer
        if async_anthropic_client and ANTHROPIC_API_KEY:
            system_prompt = (
                "You are an elite, highly precise Pakistani legal expert. Your job is to answer the user's inquiry "
                "strictly based on the provided text context data blocks. For every legal argument, case citation, or "
                "statutory rationale you provide, you must explicitly cite the corresponding case_id, court, and year from "
                "the context metadata. If the context data blocks do not contain sufficient specific information to answer "
                "the user's inquiry confidently and factually, clearly flag that the context does not contain enough "
                "information to respond securely."
            )
            
            claude_message = await async_anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2500,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Provided Context:\n{combined_context}\n\nUser Question: {request.query_text}"}
                ]
            )
            
            text_pieces = [
                getattr(block, "text", "") 
                for block in claude_message.content 
                if getattr(block, "type", None) == "text" or hasattr(block, "text")
            ]
            generated_answer = "".join(text_pieces) if text_pieces else "No text response block generated."
        else:
            # 🔄 FALLBACK SIMULATION LAYER (Allows end-to-end testing without the key)
            primary_citation = citations_payload[0]["case_id"] if citations_payload else "relevant case law"
            primary_court = citations_payload[0]["court"] if citations_payload else "the courts"
            
            generated_answer = (
                f"### Legal Evaluation (Simulated Production Environment Check)\n\n"
                f"In regards to your question: *\"{request.query_text}\"*, a search was successfully completed against "
                f"the vector index database. The primary returning precedent found is **{primary_citation}** handled by the **{primary_court}**.\n\n"
                f"This response is simulated because the `ANTHROPIC_API_KEY` is not yet provisioned in the cloud environment dashboard. "
                f"However, the entire data ingestion mapping, vector filtering coordinates, and database logging loops are fully functional.\n\n"
                f"Please use the feedback button below to submit a correction if needed to test the self-learning pipeline storage structure."
            )
        
        # 4. Push history logs straight down into Supabase tracking tables
        db_insert = supabase.table("queries").insert({
            "user_id": authenticated_user_id,
            "query_text": request.query_text,
            "answer_text": generated_answer,
            "citations": citations_payload
        }).execute()
        
        inserted_row_id = None
        if db_insert.data and isinstance(db_insert.data, list) and len(db_insert.data) > 0:
            first_row = db_insert.data[0]
            inserted_row_id = first_row.get("id") if isinstance(first_row, dict) else getattr(first_row, "id", None)
        
        if not inserted_row_id:
            inserted_row_id = str(uuid.uuid4())
        
        return {
            "answer": generated_answer,
            "citations": citations_payload,
            "query_id": inserted_row_id
        }
        
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
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
        return {"status": "feedback successfully saved for future training pipelines"}
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{user_id}")
async def get_user_history(user_id: str, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        if user_id != authenticated_user_id and authenticated_user_id != "mock_clerk_user_id_dev_run":
            raise HTTPException(status_code=403, detail="Access verification block: profile reference mismatch.")
        res = supabase.table("queries").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return res.data
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/export-training-data")
async def export_training_data():
    """🔄 SELF-LEARNING PIPELINE: Serializes manual human corrections into standard conversational JSONL data matrices."""
    try:
        feedback_res = supabase.table("feedback").select("*").execute()
        feedback_records = feedback_res.data if feedback_res else []
        if not feedback_records or not isinstance(feedback_records, list):
            return {"message": "Dataset compilation complete: 0 correction records found yet.", "jsonl_payload": []}
            
        jsonl_dataset = []
        for item in feedback_records:
            if not isinstance(item, dict):
                continue
            q_id = item.get("query_id")
            if not q_id:
                continue
            q_res = supabase.table("queries").select("query_text").eq("id", q_id).execute()
            
            if q_res and isinstance(q_res.data, list) and len(q_res.data) > 0:
                first_row = q_res.data[0]
                if isinstance(first_row, dict):
                    original_prompt = first_row.get("query_text", "")
                    corrected_output = item.get("correct_answer", "")
                    training_line = {
                        "messages": [
                            {"role": "user", "content": str(original_prompt)},
                            {"role": "assistant", "content": str(corrected_output)}
                        ]
                    }
                    jsonl_dataset.append(training_line)
                
        return {
            "total_training_records": len(jsonl_dataset),
            "format_specification": "JSON-Lines (Standard Message API mapping Layout)",
            "jsonl_payload": jsonl_dataset
        }
    except Exception as e:
        if os.environ.get("SENTRY_DSN"):
            sentry_sdk.capture_exception(e)
        raise HTTPException(status_code=500, detail=f"Failed to generate self-training dataset: {str(e)}")