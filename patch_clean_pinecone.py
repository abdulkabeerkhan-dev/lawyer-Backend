#!/usr/bin/env python3
"""
Patch & Clean Existing Pinecone Vectors Script
Iterates through vectors in Pinecone, cleans OCR typos/stamps/scanner garbage in metadata using PakistaniLegalTextCleaner,
and updates Pinecone metadata in-place.
"""

import os
import sys
import logging
from tqdm import tqdm
from pinecone import Pinecone
from cleaner import legal_cleaner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "legal-kb-pk-local")
NAMESPACE = os.getenv("PINECONE_NAMESPACE", "judgments")

def patch_existing_pinecone_vectors(batch_size: int = 100, re_embed: bool = False):
    if not PINECONE_API_KEY:
        logger.error("PINECONE_API_KEY environment variable is required.")
        sys.exit(1)

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)

    logger.info(f"Connected to Pinecone Index '{INDEX_NAME}', namespace '{NAMESPACE}'. Starting metadata cleaning patch...")

    total_patched = 0

    try:
        # Paginate through vector IDs in the target namespace
        for id_batch in index.list(namespace=NAMESPACE):
            if not id_batch:
                continue

            # Fetch existing metadata for this batch
            fetch_res = index.fetch(ids=id_batch, namespace=NAMESPACE)
            vectors = fetch_res.get("vectors", {}) if isinstance(fetch_res, dict) else getattr(fetch_res, "vectors", {}) or {}

            updates = []
            for vec_id, vec_data in vectors.items():
                meta = vec_data.get("metadata", {}) if isinstance(vec_data, dict) else getattr(vec_data, "metadata", {}) or {}
                raw_text = meta.get("text") or meta.get("text_preview") or ""

                if not raw_text:
                    continue

                cleaned_text = legal_cleaner.clean(raw_text)

                # Only update if cleaning made a meaningful change
                if cleaned_text != raw_text:
                    meta_copy = dict(meta)
                    meta_copy["text"] = cleaned_text[:15000]
                    meta_copy["text_preview"] = cleaned_text[:200]
                    meta_copy["ocr_cleaned"] = True

                    updates.append({
                        "id": vec_id,
                        "metadata": meta_copy
                    })

            if updates:
                # Update vector metadata in-place
                for u in updates:
                    try:
                        index.update(id=u["id"], set_metadata=u["metadata"], namespace=NAMESPACE)
                        total_patched += 1
                    except Exception as err:
                        logger.warning(f"Error updating vector metadata for ID '{u['id']}': {err}")

            logger.info(f"Patched {total_patched} vectors so far...")

    except Exception as e:
        logger.error(f"Error during Pinecone vector metadata patching: {e}")

    logger.info(f"Completed! Total Pinecone vector metadata records cleaned & patched: {total_patched}")

if __name__ == "__main__":
    patch_existing_pinecone_vectors()
