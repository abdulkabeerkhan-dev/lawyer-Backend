import os
import re
import hashlib
import json
import logging
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from dotenv import load_dotenv
from pinecone import Pinecone

# Re-use logic from ingest.py
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ingest import safe_year, extract_mapped_column, COLUMN_ALIASES, chunk_by_paragraph, CONTENT_COLUMN

load_dotenv()
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "judgments")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def update_vector_metadata(vector_id: str, new_year: int) -> bool:
    try:
        index.update(id=vector_id, set_metadata={"year": new_year}, namespace=NAMESPACE)
        return True
    except Exception as e:
        if "NotFound" not in str(e):
            logger.error(f"Error updating {vector_id}: {e}")
        return False

def process_file(file_path: str):
    logger.info(f"Processing {file_path} for metadata patching...")
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith('.json'):
        df = pd.read_json(file_path)
    else:
        return
    
    records = df.to_dict(orient="records")
    record_keys = list(records[0].keys()) if records else []
    
    id_col = extract_mapped_column(record_keys, "case_id")
    year_col = extract_mapped_column(record_keys, "year")
    
    if not year_col:
        logger.warning(f"No year column found in {file_path}, skipping.")
        return
        
    category_name = os.path.basename(file_path).replace('.csv', '').replace('.json', '')
    content_col = CONTENT_COLUMN if CONTENT_COLUMN and CONTENT_COLUMN in record_keys else "full_text"
    if content_col not in record_keys:
        return
        
    update_tasks = []
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = []
        for idx, row in enumerate(tqdm(records, desc=f"Scanning {file_path}")):
            main_text = str(row.get(content_col, "")).strip()
            if not main_text or main_text.lower() in ("nan", "none", ""):
                continue
                
            case_id = str(row.get(id_col, f"{category_name}-ROW-{idx}")) if id_col else f"{category_name}-ROW-{idx}"
            safe_case_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', case_id)
            
            correct_year = safe_year(row.get(year_col, 2026)) if year_col else 2026
            
            if correct_year != 2026:
                chunks = chunk_by_paragraph(main_text)
                for chunk_idx in range(len(chunks)):
                    if len(safe_case_id) > 450:
                        hash_suffix = hashlib.md5(safe_case_id.encode("utf-8")).hexdigest()
                        vector_id = f"{safe_case_id[:410]}_{hash_suffix}_chunk_{chunk_idx}"
                    else:
                        vector_id = f"{safe_case_id}_chunk_{chunk_idx}"
                    
                    futures.append(executor.submit(update_vector_metadata, vector_id, correct_year))
        
        success_count = 0
        for f in tqdm(as_completed(futures), total=len(futures), desc="Updating Pinecone"):
            if f.result():
                success_count += 1
                
        logger.info(f"Finished {file_path}. Successfully sent {success_count} vector updates.")

if __name__ == "__main__":
    import glob
    files = glob.glob("datasets/*.csv")
    for f in files:
        process_file(f)
