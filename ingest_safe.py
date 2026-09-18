import os
import sys
import re
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from supabase import create_client
from pinecone import Pinecone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("ingest_safe")

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
TARGET_NAMESPACE = "judgments"

if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY is missing from environment.")
    sys.exit(1)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import get_voyage_embedding

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if (SUPABASE_URL and SUPABASE_SERVICE_KEY) else None
pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME)

def extract_legal_sections(text: str) -> List[str]:
    if not text:
        return []
    sections = set()
    sec_matches = re.findall(r'(?i)\b(?:Section|Sect|Sec|S)\s*[\.\:]?\s*(\d+[A-Z]?(?:-[A-Z]+)?(?:\(\d+\))?)', text)
    for s in sec_matches:
        s_clean = s.upper().strip()
        if s_clean:
            sections.add(s_clean)
            base = re.sub(r'\(\d+\)', '', s_clean)
            if base and base != s_clean:
                sections.add(base)
    art_matches = re.findall(r'(?i)\b(?:Article|Art)\s*[\.\:]?\s*(\d+[A-Z]?)', text)
    for a in art_matches:
        sections.add(a.upper().strip())
    rule_matches = re.findall(r'(?i)\b(?:Rule|Order)\s*[\.\:]?\s*([IVXLCDM\d]+[A-Z]?)', text)
    for r_item in rule_matches:
        sections.add(r_item.upper().strip())
    return sorted(list(sections))

def check_citation_exists_in_pinecone(citation: str, case_id: str = "") -> bool:
    """
    Deduplication check: Query Pinecone (namespace='judgments') using metadata filter
    for exact citation or case_id before processing or embedding.
    """
    if not citation and not case_id:
        return False

    try:
        # Check by citation
        if citation:
            res_cit = pinecone_index.query(
                namespace=TARGET_NAMESPACE,
                vector=[0.01] * 1024,
                top_k=1,
                filter={"citation": {"$eq": citation}},
                include_metadata=False
            )
            matches = res_cit.get("matches", []) if isinstance(res_cit, dict) else getattr(res_cit, "matches", []) or []
            if len(matches) > 0:
                return True

        # Check by case_id
        if case_id:
            res_cid = pinecone_index.query(
                namespace=TARGET_NAMESPACE,
                vector=[0.01] * 1024,
                top_k=1,
                filter={"case_id": {"$eq": case_id}},
                include_metadata=False
            )
            matches_cid = res_cid.get("matches", []) if isinstance(res_cid, dict) else getattr(res_cid, "matches", []) or []
            if len(matches_cid) > 0:
                return True
    except Exception as err:
        logger.warning(f"Metadata deduplication query warning for '{citation}/{case_id}': {err}")

    return False

def chunk_text_token_aware(text: str, chunk_size_chars: int = 1500, overlap_chars: int = 300) -> List[str]:
    """
    Token-aware paragraph splitting around ~500 tokens (approx 1500 chars) with 300 chars overlap.
    """
    if not text:
        return []
    
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current_chunk = []
    current_len = 0

    for para in paragraphs:
        para_str = para.strip()
        if not para_str:
            continue
        
        if current_len + len(para_str) > chunk_size_chars and current_chunk:
            full_chunk_text = "\n\n".join(current_chunk)
            chunks.append(full_chunk_text)
            
            # Keep overlap paragraphs
            overlap_text = full_chunk_text[-overlap_chars:]
            current_chunk = [overlap_text, para_str]
            current_len = len(overlap_text) + len(para_str)
        else:
            current_chunk.append(para_str)
            current_len += len(para_str)

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks

async def ingest_record_safely(record: Dict[str, Any]) -> bool:
    """
    Ingests a single judgment record with deduplication, section backfilling, and batch upsert.
    """
    case_id = str(record.get("case_id") or record.get("id") or "").strip()
    citation = str(record.get("neutral_citation") or record.get("citation") or "").strip()
    case_title = str(record.get("case_title") or record.get("title") or "Reported Precedent").strip()
    court = str(record.get("court_name") or record.get("court") or "").strip()
    decision_date = str(record.get("decision_date") or record.get("year") or "").strip()
    full_text = str(record.get("full_text") or record.get("text") or "").strip()

    if not full_text:
        logger.warning(f"Skipping record {citation}/{case_id}: empty full_text.")
        return False

    # 1. Deduplication Check in Pinecone namespace 'judgments'
    if check_citation_exists_in_pinecone(citation, case_id):
        logger.info(f"⏭️ Skipping duplicate judgment: '{citation}' (case_id: {case_id}) already exists in namespace '{TARGET_NAMESPACE}'.")
        return False

    # 2. Supabase Storage (if configured)
    if supabase:
        import uuid
        supa_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, case_id)) if case_id else str(uuid.uuid4())
        try:
            supabase.table("full_judgments").upsert({
                "id": supa_id,
                "case_id": case_id,
                "neutral_citation": citation,
                "case_title": case_title,
                "court_name": court,
                "decision_date": decision_date,
                "full_text": full_text
            }).execute()
        except Exception as supa_err:
            logger.warning(f"Supabase upsert notice for {citation}: {supa_err}")

    # 3. Dynamic Section Extraction
    provided_sections = record.get("sections")
    if not provided_sections:
        extracted_sections = extract_legal_sections(full_text)
    else:
        extracted_sections = provided_sections if isinstance(provided_sections, list) else [str(provided_sections)]

    statutes = record.get("statutes", [])

    # 4. Token-aware Chunking & Batch Upsert
    chunks = chunk_text_token_aware(full_text)
    vectors = []

    for idx, chunk_text in enumerate(chunks):
        vector_id = f"{case_id}_chk_{idx}"
        chunk_sections = extract_legal_sections(chunk_text) or extracted_sections

        try:
            embedding = await get_voyage_embedding(chunk_text)
        except Exception as emb_err:
            logger.error(f"Embedding error for {vector_id}: {emb_err}")
            continue

        meta = {
            "case_id": case_id,
            "citation": citation,
            "neutral_citation": citation,
            "case_title": case_title,
            "court": court,
            "court_name": court,
            "decision_date": decision_date,
            "sections": chunk_sections,
            "statutes": statutes,
            "chunk_index": idx,
            "text": chunk_text,
            "text_content": chunk_text
        }
        vectors.append({
            "id": vector_id,
            "values": embedding,
            "metadata": meta
        })

    if vectors:
        pinecone_index.upsert(vectors=vectors, namespace=TARGET_NAMESPACE)
        logger.info(f"✅ Upserted {len(vectors)} chunks for '{citation}' into Pinecone namespace '{TARGET_NAMESPACE}'.")
        return True

    return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        if os.path.exists(input_file):
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else [data]
            logger.info(f"Processing {len(items)} items from {input_file}...")
            for item in items:
                asyncio.run(ingest_record_safely(item))
