import os
import sys
import json
import logging
import asyncio
from dotenv import load_dotenv
from supabase import create_client
from pinecone import Pinecone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ingest_2026_cases")

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
TARGET_NAMESPACE = "clean-v1"

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not PINECONE_API_KEY:
    logger.error("Missing required environment keys.")
    sys.exit(1)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import get_voyage_embedding

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME)

async def ingest_cases():
    json_path = os.path.join(os.path.dirname(__file__), "..", "input_data", "scmr_2026_cases.json")
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    logger.info(f"Loaded {len(records)} records for ingestion.")

    for record in records:
        case_id = record["case_id"]
        citation = record["neutral_citation"]
        case_title = record["case_title"]
        court = record["court_name"]
        decision_date = record["decision_date"]
        full_text = record["full_text"]
        sections = record.get("sections", [])
        statutes = record.get("statutes", [])

        # 1. Upsert to Supabase full_judgments table
        import uuid
        supabase_payload = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, case_id)),
            "case_id": case_id,
            "neutral_citation": citation,
            "case_title": case_title,
            "court_name": court,
            "decision_date": decision_date,
            "full_text": full_text
        }
        try:
            supabase.table("full_judgments").upsert(supabase_payload).execute()
            logger.info(f"✅ Upserted {citation} to Supabase full_judgments.")
        except Exception as supa_err:
            logger.error(f"Error upserting {case_id} to Supabase: {supa_err}")

        # 2. Chunk full_text into clean vector payloads
        chunks = [full_text[i:i+1500] for i in range(0, len(full_text), 1200)]
        
        vectors_to_upsert = []
        for idx, chunk_text in enumerate(chunks):
            vector_id = f"{case_id}_chk_{idx}"
            embedding = await get_voyage_embedding(chunk_text)
            
            meta = {
                "case_id": case_id,
                "citation": citation,
                "neutral_citation": citation,
                "case_title": case_title,
                "court": court,
                "court_name": court,
                "decision_date": decision_date,
                "year": 2026,
                "sections": sections,
                "statutes": statutes,
                "dataset_category": "civil",
                "chunk_index": idx,
                "text": chunk_text,
                "text_content": chunk_text
            }
            vectors_to_upsert.append({
                "id": vector_id,
                "values": embedding,
                "metadata": meta
            })

        if vectors_to_upsert:
            pinecone_index.upsert(vectors=vectors_to_upsert, namespace=TARGET_NAMESPACE)
            logger.info(f"✅ Upserted {len(vectors_to_upsert)} vector chunks for {citation} into Pinecone namespace '{TARGET_NAMESPACE}'.")

if __name__ == "__main__":
    asyncio.run(ingest_cases())
