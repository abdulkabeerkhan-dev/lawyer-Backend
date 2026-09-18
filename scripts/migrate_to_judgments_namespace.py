import os
import sys
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from pinecone import Pinecone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("migrate_judgments")

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
SOURCE_NAMESPACE = "clean-v1"
TARGET_NAMESPACE = "judgments"

if not PINECONE_API_KEY:
    logger.error("PINECONE_API_KEY is missing from environment.")
    sys.exit(1)

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

def extract_legal_sections(text: str) -> list[str]:
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

def migrate_batch(vec_ids: list[str]) -> int:
    copied = 0
    try:
        fetched = index.fetch(ids=vec_ids, namespace=SOURCE_NAMESPACE)
        vectors_map = fetched.get("vectors", {}) if isinstance(fetched, dict) else getattr(fetched, "vectors", {}) or {}
        
        upsert_payload = []
        for vid, vdata in vectors_map.items():
            vals = vdata.get("values") if isinstance(vdata, dict) else getattr(vdata, "values", None)
            meta = vdata.get("metadata", {}) if isinstance(vdata, dict) else getattr(vdata, "metadata", {}) or {}
            
            # Ensure text field consistency
            text_content = meta.get("text_content") or meta.get("text") or meta.get("preview") or ""
            meta["text"] = text_content
            meta["text_content"] = text_content
            
            # Dynamic section extraction if None or empty
            existing_sections = meta.get("sections")
            if not existing_sections:
                extracted = extract_legal_sections(text_content)
                meta["sections"] = extracted if extracted else []
            
            if vals:
                upsert_payload.append({
                    "id": vid,
                    "values": vals,
                    "metadata": meta
                })
        
        if upsert_payload:
            index.upsert(vectors=upsert_payload, namespace=TARGET_NAMESPACE)
            copied = len(upsert_payload)
    except Exception as e:
        logger.error(f"Error migrating batch of {len(vec_ids)} vectors: {e}")
    
    return copied

def run_migration():
    logger.info(f"Starting namespace migration & section backfill from '{SOURCE_NAMESPACE}' to '{TARGET_NAMESPACE}'...")
    
    all_ids = []
    for id_page in index.list(namespace=SOURCE_NAMESPACE):
        for item in id_page:
            vid = item.id if hasattr(item, 'id') else str(item)
            all_ids.append(vid)
    
    total_vectors = len(all_ids)
    logger.info(f"Total vectors found in source namespace '{SOURCE_NAMESPACE}': {total_vectors}")
    
    batch_size = 50
    batches = [all_ids[i:i + batch_size] for i in range(0, len(all_ids), batch_size)]
    
    total_copied = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(migrate_batch, b) for b in batches]
        completed = 0
        for fut in as_completed(futures):
            c = fut.result()
            total_copied += c
            completed += 1
            if completed % 50 == 0 or completed == len(batches):
                logger.info(f"Progress: {completed}/{len(batches)} batches processed. Total Copied to '{TARGET_NAMESPACE}': {total_copied}")
    
    logger.info(f"Migration Complete! Total Vectors in '{TARGET_NAMESPACE}': {total_copied}")

if __name__ == "__main__":
    run_migration()
