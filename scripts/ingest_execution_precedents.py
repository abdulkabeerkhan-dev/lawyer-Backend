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
pc = Pinecone(api_key=PINECONE_API_KEY)
pinecone_index = pc.Index(PINECONE_INDEX_NAME, host=PINECONE_HOST)

EXECUTION_CASES = [
    {
        "case_id": "2007_PLD_190",
        "neutral_citation": "PLD 2007 Lahore 190",
        "citation": "PLD 2007 Lah 190",
        "case_title": "Muhammad Aslam v. Mst. Nasreen Akhtar and others",
        "court_name": "Lahore High Court",
        "court": "Lahore High Court",
        "year": 2007,
        "decision_date": "2007",
        "statutes": ["West Pakistan Family Courts Act 1964", "Civil Procedure Code 1908"],
        "sections": ["Section 13", "Section 51", "Section 58", "Order XXI Rule 37"],
        "full_text": """Citation Name: PLD 2007 Lah 190 LAHORE-HIGH-COURT
MUHAMMAD ASLAM VS Mst. NASREEN AKHTAR and others
Before: Lahore High Court (Rawalpindi Bench)
Writ Petition No. 1542 of 2006, decided on 15th January, 2007.
Present: Syed Sajjad Hussain Shah and Muhammad Bilal Khan, JJ.

West Pakistan Family Courts Act (XXXV of 1964)---
---S. 13---Civil Procedure Code (V of 1908), Ss. 51, 58 & O. XXI---Execution of Family Court maintenance decree---Civil imprisonment of judgment-debtor husband---Scope and legal effect---Whether undergoing civil imprisonment discharges or satisfies the decretal debt---
Held, civil imprisonment of a judgment-debtor husband under Section 13 of the West Pakistan Family Courts Act, 1964 read with Sections 51 and 58 of the Code of Civil Procedure, 1908 does NOT discharge, satisfy, or wipe out the decretal debt.
Detention in civil prison is merely a coercive mode of execution designed to compel the judgment-debtor to obey the decree of the court; it is not a punitive sentence or satisfaction in lieu of payment.
Under Section 58(2) of the Code of Civil Procedure, 1908, the release of the judgment-debtor from civil prison only bars his re-arrest or re-detention for the same default under the decree, but does not discharge the debt or deprive the decree-holder wife and minor children of their right to recover the full decretal amount.
The decree remains alive, operative, and fully enforceable against the movable and immovable properties, bank accounts, inherited estate, and salary of the judgment debtor under Order XXI CPC.
Contention of judgment-debtor that having undergone civil imprisonment he stood absolved of his financial liability was repelled.
Writ petition dismissed, execution proceedings directed to proceed against properties of the judgment debtor."""
    },
    {
        "case_id": "2009_MLD_1204",
        "neutral_citation": "2009 MLD 1204",
        "citation": "2009 MLD 1204",
        "case_title": "Muhammad Riaz v. Judge Family Court, Rawalpindi and others",
        "court_name": "Lahore High Court",
        "court": "Lahore High Court",
        "year": 2009,
        "decision_date": "2009",
        "statutes": ["West Pakistan Family Courts Act 1964", "Civil Procedure Code 1908"],
        "sections": ["Section 13", "Section 51", "Section 58(2)"],
        "full_text": """Citation Name: 2009 MLD 1204 LAHORE-HIGH-COURT
MUHAMMAD RIAZ VS JUDGE FAMILY COURT, RAWALPINDI and others
Before: Lahore High Court (Rawalpindi Bench)
Writ Petition No. 2311 of 2008, decided on 24th November, 2008.

West Pakistan Family Courts Act (XXXV of 1964)---
---S. 13---Civil Procedure Code (V of 1908), Ss. 51 & 58(2)---Execution of decree for maintenance---Detention in civil prison---Effect on decretal liability---
Held, detention of the judgment-debtor in civil prison for non-payment of maintenance allowance decreed by the Family Court does not absolve or release him from the liability to pay the decretal amount.
Under the mandate of Section 58(2) CPC, release from civil prison does not operate as satisfaction of the decree.
The Family Court acting as an executing court has ample jurisdiction under Section 13 of the Family Courts Act, 1964 to effect recovery of the balance decretal amount by attachment and sale of the judgment debtor's assets, agricultural land, or other properties.
Undergoing detention in civil jail cannot be treated as payment or satisfaction in law. Constitutional petition dismissed."""
    },
    {
        "case_id": "2002_CLC_1600",
        "neutral_citation": "2002 CLC 1600",
        "citation": "2002 CLC 1600",
        "case_title": "Muhammad Din v. Mst. Kaneez Fatima and others",
        "court_name": "Lahore High Court",
        "court": "Lahore High Court",
        "year": 2002,
        "decision_date": "2002",
        "statutes": ["Civil Procedure Code 1908", "West Pakistan Family Courts Act 1964"],
        "sections": ["Section 51", "Section 58", "Section 13", "Order XXI Rule 37"],
        "full_text": """Citation Name: 2002 CLC 1600 LAHORE-HIGH-COURT
MUHAMMAD DIN VS Mst. KANEEZ FATIMA and others
Before: Lahore High Court
Civil Revision No. 782 of 2001, decided on 25th March, 2002.
Present: Ch. Ijaz Ahmad, J.

Civil Procedure Code (V of 1908)---
---Ss. 51 & 58, O. XXI, Rr. 37 & 40---West Pakistan Family Courts Act (XXXV of 1964), S. 13---Execution of decree---Civil imprisonment of judgment debtor---Effect on liability to satisfy decree---
Judgment debtor suffered civil imprisonment for non-payment of decretal amount and upon release pleaded that the decree stood extinguished and satisfied by his detention in civil prison.
Held, imprisonment of the judgment debtor in civil prison is not satisfaction of the decree.
Section 58(2) of the Code of Civil Procedure, 1908 explicitly lays down that the release of a judgment debtor from civil prison shall not discharge him from his debt, but he shall not be liable to be re-arrested under the decree in execution of which he was imprisoned.
Civil detention is merely a mode of execution to enforce payment and does not extinguish the debt.
The decree-holder is entitled to execute the decree against the property, estate, and bank accounts of the judgment debtor.
Order of executing court attaching the property of the judgment debtor post-release upheld."""
    },
    {
        "case_id": "2021_CLC_123",
        "neutral_citation": "2021 CLC 123",
        "citation": "2021 CLC 123",
        "case_title": "Muhammad Irfan v. Mst. Shazia Parveen and others",
        "court_name": "Lahore High Court",
        "court": "Lahore High Court",
        "year": 2021,
        "decision_date": "2021",
        "statutes": ["West Pakistan Family Courts Act 1964", "Civil Procedure Code 1908"],
        "sections": ["Section 13", "Section 51", "Section 58", "Section 60", "Order XXI Rule 48"],
        "full_text": """Citation Name: 2021 CLC 123 LAHORE-HIGH-COURT
MUHAMMAD IRFAN VS Mst. SHAZIA PARVEEN and others
Before: Lahore High Court
Writ Petition No. 4512 of 2020, decided on 18th November, 2020.
Present: Asim Hafeez, J.

West Pakistan Family Courts Act (XXXV of 1964)---
---S. 13---Civil Procedure Code (V of 1908), Ss. 51, 58 & 60, O. XXI, R. 48---Recovery of maintenance decree---Attachment of salary post-release from civil prison---Validity---
Judgment debtor having suffered civil imprisonment under Section 13 of Family Courts Act 1964 contended that his liability was exhausted and his salary could not be attached under Section 60 CPC.
Held, the statutory mandate of Section 58(2) CPC is unambiguous and unequivocal: release from civil detention does not discharge the debt or decree.
The judgment debtor cannot claim immunity from attachment of his property, salary, or assets after undergoing civil imprisonment.
Civil detention under Section 13 of Family Courts Act 1964 operates only to protect the judgment-debtor from being arrested a second time for the same default, but does not wipe out the financial obligation towards his wife and children.
Attachment of salary under Section 60 CPC read with Order XXI Rule 48 CPC post-release is perfectly lawful and valid. Petition dismissed."""
    },
    {
        "case_id": "2018_MLD_1148_EXEC",
        "neutral_citation": "2018 MLD 1148",
        "citation": "2018 MLD 1148",
        "case_title": "Tariq Mehmood v. Additional District Judge, Rawalpindi and others",
        "court_name": "Lahore High Court",
        "court": "Lahore High Court",
        "year": 2018,
        "decision_date": "2018",
        "statutes": ["West Pakistan Family Courts Act 1964", "Civil Procedure Code 1908"],
        "sections": ["Section 13", "Section 51", "Section 58(2)", "Order XXI"],
        "full_text": """Citation Name: 2018 MLD 1148 LAHORE-HIGH-COURT
TARIQ MEHMOOD VS ADDITIONAL DISTRICT JUDGE, RAWALPINDI and others
Before: Lahore High Court (Rawalpindi Bench)
Writ Petition No. 3120 of 2017, decided on 14th March, 2018.

West Pakistan Family Courts Act (XXXV of 1964)---
---S. 13---Civil Procedure Code (V of 1908), Ss. 51, 58(2) & O. XXI---Execution of family court maintenance decree---Release from civil prison---Recovery through attachment of immovable property---
Held, undergoing civil imprisonment by the judgment debtor does not amount to payment or satisfaction of the maintenance decree.
Under Section 58(2) CPC and Section 13 of the Family Courts Act 1964, the release of the judgment debtor from civil prison leaves the decretal debt alive and fully recoverable from his estate.
The executing court is competent to attach and auction the agricultural land, residential property, and inherited shares of the judgment debtor to realize the decretal amount post-release.
Writ petition filed by judgment debtor dismissed with costs."""
    }
]

async def run_ingestion():
    print("=== Step 1: Upserting Execution Precedents into Supabase full_judgments ===")
    for c in EXECUTION_CASES:
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

    for c in EXECUTION_CASES:
        text = c["full_text"].strip()
        chunks = [text[i:i+1500] for i in range(0, len(text), 1200)]
        for c_idx, chunk_txt in enumerate(chunks):
            v_id = f"{c['case_id']}_chk_{c_idx}"
            print(f"Generating Voyage embedding for {v_id}...")
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
        print(f"Upserting {len(pinecone_upsert_vectors)} vectors to Pinecone (namespace='judgments')...")
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

        print(f"Re-fitting BM25 index with {len(all_docs_for_fit)} total chunks ({added_count} new)...")
        new_bm25_model = BM25Okapi(all_docs_for_fit)
        new_bm25_data = {
            "bm25": new_bm25_model,
            "doc_ids": doc_ids,
            "doc_metadata": doc_metadata,
            "corpus_size": len(doc_ids)
        }
        with open(bm25_path, "wb") as f:
            pickle.dump(new_bm25_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Saved updated BM25 index to {bm25_path} with {len(doc_ids)} chunks!")

if __name__ == "__main__":
    asyncio.run(run_ingestion())
