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
logger = logging.getLogger("backfill_sections")

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
TARGET_NAMESPACE = "clean-v1"

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

def process_batch(vec_ids: list[str]) -> tuple[int, int]:
    updated_count = 0
    skipped_count = 0
    try:
        fetched = index.fetch(ids=vec_ids, namespace=TARGET_NAMESPACE)
        vectors_map = fetched.get("vectors", {}) if isinstance(fetched, dict) else getattr(fetched, "vectors", {}) or {}
        
        for vid, vdata in vectors_map.items():
            meta = vdata.get("metadata", {}) if isinstance(vdata, dict) else getattr(vdata, "metadata", {}) or {}
            text_content = meta.get("text_content") or meta.get("text") or meta.get("preview") or ""
            sections = extract_legal_sections(text_content)
            
            # Perform update on metadata if sections found
            if sections:
                try:
                    index.update(
                        id=vid,
                        set_metadata={"sections": sections},
                        namespace=TARGET_NAMESPACE
                    )
                    updated_count += 1
                except Exception as update_err:
                    logger.warning(f"Error updating vector {vid}: {update_err}")
            else:
                skipped_count += 1
    except Exception as e:
        logger.error(f"Error fetching batch of {len(vec_ids)} vectors: {e}")
    
    return updated_count, skipped_count

def run_backfill():
    logger.info(f"Starting metadata sections backfill for namespace '{TARGET_NAMESPACE}'...")
    
    # 1. Collect all vector IDs in namespace
    all_ids = []
    logger.info("Listing all vector IDs in namespace...")
    for id_page in index.list(namespace=TARGET_NAMESPACE):
        for item in id_page:
            vid = item.id if hasattr(item, 'id') else str(item)
            all_ids.append(vid)
    
    total_vectors = len(all_ids)
    logger.info(f"Total vectors found in namespace '{TARGET_NAMESPACE}': {total_vectors}")
    
    batch_size = 50
    batches = [all_ids[i:i + batch_size] for i in range(0, len(all_ids), batch_size)]
    
    total_updated = 0
    total_skipped = 0
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_batch, b) for b in batches]
        completed = 0
        for fut in as_completed(futures):
            up, skip = fut.result()
            total_updated += up
            total_skipped += skip
            completed += 1
            if completed % 50 == 0 or completed == len(batches):
                logger.info(f"Progress: {completed}/{len(batches)} batches processed. Updated: {total_updated}, Skipped: {total_skipped}")
    
    logger.info(f"Backfill Complete! Total Updated: {total_updated}, Total Skipped: {total_skipped}")

if __name__ == "__main__":
    run_backfill()
