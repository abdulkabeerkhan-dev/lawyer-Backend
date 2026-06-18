import os
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import httpx
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from pinecone import Pinecone
from anthropic import AsyncAnthropic
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load local testing configurations
load_dotenv()

# 🛡️ SENTRY SYSTEM LOG ENGINE: Production exception diagnostics activation
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(title="TO BE NAMED AI LAWYER - Local Embedding Production Server")

# 🔒 SECURITY ACCESS CORE: Cross-Origin Resource Sharing gateway adjustments
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Production Cloud Infrastructures
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
# Match this configuration directly to your new 1024-dimension standard index space
pinecone_index = pc.Index(os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local"))

# Shift completely to the asynchronous client to maximize parallel API capabilities
async_anthropic_client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL", ""),
    os.environ.get("SUPABASE_SERVICE_KEY", "")
)

# Initialize Identity Token Extractor Agent
security_agent = HTTPBearer()

# 🧠 LOCAL SEARCH ALIGNMENT ENGINE: Load matching copy of model for incoming query vector metrics
try:
    local_retrieval_encoder = SentenceTransformer("BAAI/bge-large-en-v1.5")
except Exception as model_error:
    raise RuntimeError(f"Server initialization blocked: could not spin up open-source embedding layer: {model_error}")

async def verify_clerk_session(credentials: HTTPAuthorizationCredentials = Depends(security_agent)) -> str:
    """
    🔐 CLERK IDENTITY BOUNDARY: Intercepts connection frames,
    cross-verifies keys with central authorization databases, and returns confirmed user tags.
    """
    token = credentials.credentials
    
    # 🧪 ISOLATED LOCAL SANDBOX BYPASS
    if os.environ.get("FRONTEND_URL", "*") == "*":
        return "mock_clerk_user_id_dev_run"
        
    clerk_api_url = "https://api.clerk.dev/v1/tokens/verify"
    async with httpx.AsyncClient() as client:
        try:
            headers = {"Authorization": f"Bearer {os.environ.get('CLERK_SECRET_KEY')}"}
            response = await client.post(clerk_api_url, json={"token": token}, headers=headers)
            if response.status_code != 200:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clerk security session evaluation failed.")
            
            data = response.json()
            return str(data.get("user_id", ""))
        except Exception as error_context:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication block interrupted routing layer: {str(error_context)}")

# Data Transport Verification Forms
class QueryRequest(BaseModel):
    query_text: str

class FeedbackRequest(BaseModel):
    query_id: str
    original_answer: str
    correct_answer: str

@app.get("/health")
def health_check():
    """Used by Railway lifecycle observers to verify cluster fitness status."""
    return {"status": "healthy"}

@app.post("/query")
async def execute_legal_query(request: QueryRequest, authenticated_user_id: str = Depends(verify_clerk_session)):
    try:
        # 1. Compute incoming search coordinates locally with zero third-party latency or pricing overhead
        # Add the bge query prefix to optimize searching across paragraph blocks correctly
        bge_query_text = f"Represent this sentence for searching relevant passages: {request.query_text}"
        query_vector = local_retrieval_encoder.encode(bge_query_text, convert_to_numpy=True).tolist()
        
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
        
        # 3. System Prompt directives mapping legal reasoning behaviors
        system_prompt = (
            "You are an elite, highly precise Pakistani legal expert. Your job is to answer the user's inquiry "
            "strictly based on the provided text context data blocks. For every legal argument, case citation, or "
            "statutory rationale you provide, you must explicitly cite the corresponding case_id, court, and year from "
            "the context metadata. If the context data blocks do not contain sufficient specific information to answer "
            "the user's inquiry confidently and factually, clearly flag that the context does not contain enough "
            "information to respond securely."
        )
        
        # 4. Asynchronous connection execution down to Claude models to avoid event loop jamming
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
        
        # 5. Push history logs straight down into Supabase tracking tables
        db_insert = supabase.table("queries").insert({
            "user_id": authenticated_user_id,
            "query_text": request.query_text,
            "answer_text": generated_answer,
            "citations": citations_payload
        }).execute()
        
        if db_insert.data and isinstance(db_insert.data, list) and len(db_insert.data) > 0:
            first_row = db_insert.data[0]
            inserted_row_id = first_row.get("id") if isinstance(first_row, dict) else getattr(first_row, "id", None)
        else:
            raise HTTPException(status_code=500, detail="Supabase transactions failed to return confirmations on record creation.")
        
        if not inserted_row_id:
            raise HTTPException(status_code=500, detail="Record processed successfully but storage confirmation serial key parsing failed.")
        
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