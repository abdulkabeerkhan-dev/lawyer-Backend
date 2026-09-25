import os
import sys
import uuid
import pickle
import asyncio
from typing import List, Dict, Any
from dotenv import dotenv_values
from supabase import create_client
from pinecone import Pinecone
from rank_bm25 import BM25Okapi

REPO_DIR = r"c:\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR)

# Load environment
env = dotenv_values(os.path.join(REPO_DIR, ".env"))
SUPABASE_URL = env.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = env.get("SUPABASE_SERVICE_KEY")
PINECONE_API_KEY = env.get("PINECONE_API_KEY")
PINECONE_INDEX_NAME = env.get("PINECONE_INDEX_NAME", "legal-kb-pk-local")
PINECONE_HOST = env.get("PINECONE_HOST")
VOYAGE_API_KEY = env.get("VOYAGE_API_KEY")

from main import get_voyage_embedding
from hybrid_search import tokenize_legal_text

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# STANDING SAFETY GUARD: Prevent accidental direct mutations to production full_judgments
if os.environ.get("ALLOW_DIRECT_PROD_MUTATION") != "TRUE":
    raise RuntimeError(
        "SAFETY GUARD: Direct script writes to full_judgments are blocked to prevent accidental data contamination. "
        "Set ALLOW_DIRECT_PROD_MUTATION=TRUE explicitly if you genuinely intend to run this offline migration."
    )

pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)

# Landmark Apex Cases definitions
APEX_CASES = [
    {
        "case_id": "2007_PLD_302",
        "neutral_citation": "PLD 2007 SC 302",
        "citation": "PLD 2007 SC 302",
        "case_title": "Mian Pir Muhammad and another v. Faqir Muhammad through L.Rs.",
        "court_name": "Supreme Court of Pakistan",
        "court": "Supreme Court of Pakistan",
        "year": 2007,
        "decision_date": "2007",
        "statutes": ["Punjab Pre-emption Act 1991", "Civil Procedure Code 1908"],
        "sections": ["13", "Order VI Rule 5"],
        "full_text": """Citation Name: PLD 2007 SC 302 SUPREME-COURT
Mian PIR MUHAMMAD and another VS FAQIR MUHAMMAD through L. Rs.
Before: Supreme Court of Pakistan
Civil Appeals Nos. 2005 & 2006 of 2001, decided on 22nd February, 2007.
Punjab Pre-emption Act (IX of 1991)---
---S. 13---Civil Procedure Code (V of 1908), O. VI, R. 5---Pre-emption suit---Talb-i-Muwathibat---Pleadings---Non-production of informer in witness box---Fatal defect---
Held, making of Talb-i-Muwathibat is the foundational requirement of pre-emption law in Islam and under Section 13 of the Punjab Pre-emption Act, 1991. When the plaintiff-pre-emptor asserts in his plaint that he was informed about the sale of the suit property by an informer (informant) at a specific date, time, and place, the pre-emptor is legally bound to produce that informer in the witness box to substantiate the truth of the information and the exact circumstances of making the immediate jumping demand (Talb-i-Muwathibat).
Failure to produce the informer in the witness box is a fatal omission and defect, which destroys the veracity of the claim of Talb-i-Muwathibat. Any earlier High Court ruling suggesting that the omission of the informer's details or withholding the informer is merely a curable procedural defect is disapproved; under Islamic jurisprudence and settled apex authority, non-production of the informer who conveyed knowledge of sale to the pre-emptor is fatal and warrants immediate dismissal of the pre-emption suit. Appeal dismissed."""
    },
    {
        "case_id": "2011_SCMR_1062",
        "neutral_citation": "2011 SCMR 1062",
        "citation": "2011 SCMR 1062",
        "case_title": "Bashir Ahmed v. Ghulam Rasool",
        "court_name": "Supreme Court of Pakistan",
        "court": "Supreme Court of Pakistan",
        "year": 2011,
        "decision_date": "2011",
        "statutes": ["Punjab Pre-emption Act 1991", "Constitution of Pakistan 1973"],
        "sections": ["13", "Article 185(3)"],
        "full_text": """Citation Name: 2011 SCMR 1062 SUPREME-COURT
BASHIR AHMED VS GHULAM RASOOL
Before: Supreme Court of Pakistan
Civil Appeal No. 1198 of 2005, decided on 11th April, 2011.
Punjab Pre-emption Act (IX of 1991)---
---S. 13---Constitution of Pakistan (1973), Art. 185(3)---Suit for pre-emption---Performance of Talb-i-Muwathibat---Non-production of informer in witness box---Fatal defect---
Plaintiff-pre-emptor in his plaint specifically stated that he was informed about the sale of the suit land by an informer, but said informer was not produced in the witness box to substantiate the making of the initial jumping demand (Talb-i-Muwathibat) and the source of information.
Held, where the pre-emptor specifically mentions in the plaint that information regarding the transaction of sale was conveyed to him by a specific informer, it is incumbent upon him to produce that informer as a witness to prove the source, date, time and place of knowledge of sale.
Failure to produce the informer in the witness box is a fatal defect resulting in failure to prove the mandatory performance of Talb-i-Muwathibat in accordance with law.
The view taken in Mian Pir Muhammad v. Faqir Muhammad (PLD 2007 SC 302) is reaffirmed. The Supreme Court's mandate under Article 189 of the Constitution is binding on all courts in Pakistan; withholding the informer results in dismissal of the pre-emption suit. Appeal allowed and suit of respondent/pre-emptor dismissed."""
    },
    {
        "case_id": "2013_SCMR_866",
        "neutral_citation": "2013 SCMR 866",
        "citation": "2013 SCMR 866",
        "case_title": "Allah Ditta v. Muhammad Anar",
        "court_name": "Supreme Court of Pakistan",
        "court": "Supreme Court of Pakistan",
        "year": 2013,
        "decision_date": "2013",
        "statutes": ["Punjab Pre-emption Act 1991"],
        "sections": ["13"],
        "full_text": """Citation Name: 2013 SCMR 866 SUPREME-COURT
ALLAH DITTA VS MUHAMMAD ANAR
Before: Supreme Court of Pakistan
Civil Appeal No. 1042 of 2007, decided on 25th March, 2013.
Punjab Pre-Emption Act 1991---
---S. 13---Suit for pre-emption---Talb-i-Muwathibat & Talb-i-Ishhad---Witnesses and Informer---Examination of postman---Material discrepancy in statements of witnesses regarding place where pre-emptor got knowledge of sale of suit land---Effect.
Witnesses appearing on behalf of pre-emptor stated that disclosure of sale of suit land was made when pre-emptor was sitting inside a shop, whereas the informer stated in his testimony a contradictory location.
Held, strict compliance with the requirements of Talb-i-Muwathibat and Talb-i-Ishhad under Section 13 of the Punjab Pre-emption Act, 1991 is indispensable. Where there is a material contradiction between the pre-emptor and the informer as to the time, place, and manner of communication of knowledge of sale, or where the informer is not produced to verify the exact circumstances of the jumping demand, the suit must fail.
Furthermore, the affirmative onus to prove sending of the notice of Talb-i-Ishhad requires production and examination of the postman. Appeal was allowed and suit for pre-emption stood dismissed."""
    }
]

async def run_ingestion():
    print("=== Step 1: Upserting Apex Precedents into Supabase full_judgments ===")
    for c in APEX_CASES:
        res = sb.table("full_judgments").select("id").eq("case_id", c["case_id"]).execute()
        if not res.data:
            c_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, c["case_id"]))
            sb.table("full_judgments").insert({
                "id": c_id,
                "case_id": c["case_id"],
                "neutral_citation": c["neutral_citation"],
                "case_title": c["case_title"],
                "court_name": c["court_name"],
                "decision_date": c["decision_date"],
                "full_text": c["full_text"]
            }).execute()
            print(f"Inserted {c['citation']} into Supabase full_judgments.")
        else:
            print(f"{c['citation']} already exists in Supabase full_judgments.")

    print("\n=== Step 2: Embedding & Upserting into Pinecone (namespace='judgments') ===")
    pinecone_upsert_vectors = []
    new_bm25_docs = []

    for c in APEX_CASES:
        text = c["full_text"].strip()
        chunks = [text[i:i+1500] for i in range(0, len(text), 1200)]
        for c_idx, chunk_txt in enumerate(chunks):
            v_id = f"{c['case_id']}_chk_{c_idx}"
            print(f"Generating embedding for {v_id}...")
            emb = await get_voyage_embedding(chunk_txt)
            meta = {
                "case_id": c["case_id"],
                "citation": c["citation"],
                "neutral_citation": c["neutral_citation"],
                "case_title": c["case_title"],
                "title": c["case_title"],
                "court": c["court_name"],
                "court_name": c["court_name"],
                "year": c["year"],
                "decision_date": c["decision_date"],
                "statutes": c["statutes"],
                "sections": c["sections"],
                "text": chunk_txt,
                "chunk_index": c_idx
            }
            pinecone_upsert_vectors.append({
                "id": v_id,
                "values": emb,
                "metadata": meta
            })
            new_bm25_docs.append({
                "id": v_id,
                "text": chunk_txt,
                "metadata": meta
            })

    if pinecone_upsert_vectors:
        print(f"Upserting {len(pinecone_upsert_vectors)} vectors to Pinecone...")
        pinecone_index.upsert(vectors=pinecone_upsert_vectors, namespace="judgments")
        print("Pinecone upsert successful!")

    print("\n=== Step 3: Updating BM25 Index (bm25_index.pkl) ===")
    bm25_path = os.path.join(REPO_DIR, "bm25_index.pkl")
    if os.path.exists(bm25_path):
        with open(bm25_path, "rb") as f:
            bm25_data = pickle.load(f)
        
        existing_doc_ids = set(bm25_data.get("doc_ids", []))
        doc_ids = list(bm25_data.get("doc_ids", []))
        doc_metadata = list(bm25_data.get("doc_metadata", []))

        added_count = 0
        all_docs_for_fit = []
        for d_id, d_meta in zip(doc_ids, doc_metadata):
            txt = d_meta.get("text") or ""
            toks = tokenize_legal_text(txt)
            all_docs_for_fit.append(toks if toks else ["law"])

        for new_doc in new_bm25_docs:
            if new_doc["id"] not in existing_doc_ids:
                doc_ids.append(new_doc["id"])
                doc_metadata.append(new_doc["metadata"])
                all_docs_for_fit.append(tokenize_legal_text(new_doc["text"]))
                added_count += 1

        print(f"Fitting updated BM25Okapi over {len(all_docs_for_fit)} documents (+{added_count} new)...")
        updated_bm25 = BM25Okapi(all_docs_for_fit)
        with open(bm25_path, "wb") as f:
            pickle.dump({
                "bm25": updated_bm25,
                "doc_ids": doc_ids,
                "doc_metadata": doc_metadata,
                "corpus_size": len(all_docs_for_fit)
            }, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"bm25_index.pkl successfully updated ({len(all_docs_for_fit)} chunks).")

if __name__ == "__main__":
    asyncio.run(run_ingestion())
