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

NARCOTICS_CASES = [
    {
        "case_id": "2015_SCMR_1002",
        "neutral_citation": "2015 SCMR 1002",
        "citation": "2015 SCMR 1002",
        "case_title": "Ikramullah and others v. The State",
        "court_name": "Supreme Court of Pakistan",
        "court": "Supreme Court of Pakistan",
        "year": 2015,
        "decision_date": "2015",
        "statutes": ["Control of Narcotic Substances Act 1997", "Code of Criminal Procedure 1898", "Qanun-e-Shahadat Order 1984"],
        "sections": ["Section 9(c)", "Section 51", "Article 185(3)"],
        "full_text": """Citation Name: 2015 SCMR 1002 SUPREME-COURT
IKRAMULLAH and others VS THE STATE
Before: Supreme Court of Pakistan
Criminal Appeals Nos. 278 and 279 of 2014, decided on 13th April, 2015.
(On appeal from judgment dated 10-6-2014 of Lahore High Court, Rawalpindi Bench)
Present: Asif Saeed Khan Khosa, Dost Muhammad Khan and Umar Ata Bandial, JJ.

Control of Narcotic Substances Act (XXV of 1997)---
---Ss. 9(c) & 51---Code of Criminal Procedure (V of 1898), S. 103---Qanun-e-Shahadat Order (10 of 1984), Art. 129, illus. (g)---Recovery of narcotics---Safe custody of contraband and safe transmission of sample parcels to Chemical Examiner---Chain of custody---Mandatory requirements---Effect of non-examination of Moharrir and carrier of samples---
Held, in a prosecution under the Control of Narcotic Substances Act, 1997, the prosecution is legally bound to establish by credible, cogent and confidence-inspiring evidence the safe custody of the recovered narcotic substance and safe transmission of the representative sample parcels to the Chemical Examiner from the very spot of recovery till receipt in the laboratory.
Safe custody of the contraband and safe transmission of samples to the Chemical Examiner are mandatory, foundational links in the evidentiary chain of custody.
Where the Moharrir (Malkhana incharge) of the police station with whom the recovered substance/sample parcels were allegedly deposited was not produced or examined as a witness in court, and the official who allegedly transmitted the sample parcels from the police station to the office of the Chemical Examiner was also not examined by the prosecution, the chain of custody is irreparably snapped and broken.
Held further, when the chain of custody is broken through failure to examine the Moharrir and the carrier official, the report of the Chemical Examiner is rendered completely inadmissible and devoid of evidentiary value. An accused person cannot be convicted under Section 9(c) of the CNSA 1997 on the basis of a Chemical Examiner's report whose provenance and uninterrupted safe transmission has not been established beyond reasonable doubt, even if the report of the Chemical Examiner is positive for charas/heroin/opium.
In the absence of safe custody and safe transmission being proved by examining the Malkhana Moharrir and transmitting police official, the prosecution fails to establish that the contraband seized was the very material examined by the Chemical Examiner.
Adverse inference under Article 129, illustration (g) of Qanun-e-Shahadat Order, 1984 arises against the prosecution for withholding the material witnesses of custody and transmission.
Appeals allowed, conviction and sentence set aside, and accused acquitted of all charges."""
    },
    {
        "case_id": "2018_SCMR_2039",
        "neutral_citation": "2018 SCMR 2039",
        "citation": "2018 SCMR 2039",
        "case_title": "The State through Regional Director ANF v. Imam Bakhsh and others",
        "court_name": "Supreme Court of Pakistan",
        "court": "Supreme Court of Pakistan",
        "year": 2018,
        "decision_date": "2018",
        "statutes": ["Control of Narcotic Substances Act 1997", "Control of Narcotic Substances (Government Analysts) Rules 2001"],
        "sections": ["Section 9(c)", "Section 20", "Section 21", "Section 22", "Section 36", "Section 51"],
        "full_text": """Citation Name: 2018 SCMR 2039 SUPREME-COURT
THE STATE through Regional Director, Anti-Narcotics Force, Rawalpindi VS IMAM BAKHSH and others
Before: Supreme Court of Pakistan
Criminal Appeal No. 27-P of 2018, decided on 12th July, 2018.
(On appeal from order dated 28-2-2018 of Peshawar High Court, Peshawar)
Present: Asif Saeed Khan Khosa, C.J., Dost Muhammad Khan and Yahya Afridi, JJ.

Control of Narcotic Substances Act (XXV of 1997)---
---Ss. 9(c), 20, 21, 22, 36 & 51---Control of Narcotic Substances (Government Analysts) Rules, 2001, Rr. 4 & 5---Appreciation of evidence---Safe custody and safe transmission of samples---Chain of custody protocol in narcotics prosecutions---Comprehensive principles laid down by Supreme Court:
(1) Recovery and seizure of narcotic substance at the spot and drawing of representative samples;
(2) Weighment, sealing and preparation of recovery memo;
(3) Movement of the recovered contraband and samples from spot to Police Station / ANF Police Station;
(4) Deposit of bulk narcotic substance and sample parcels into Malkhana under the charge of Moharrir;
(5) Entries in Register No. 19 of the Malkhana demonstrating safe custody without possibility of tampering;
(6) Handing over of sealed sample parcels to a designated police / ANF official for delivery to Chemical Examiner / Forensic Science Agency;
(7) Safe transmission and delivery by carrier official to the Chemical Examiner within the prescribed timeline without tampering;
(8) Testing and examination by the Government Analyst.
Held, in prosecutions under CNSA 1997, each and every link in the chain of custody must be proved by the prosecution beyond reasonable doubt.
If the prosecution fails to examine the Moharrir of the Malkhana or the official who transmitted the sample parcels to the Chemical Examiner, a fatal gap is created in the chain of custody.
Under the authoritative doctrine of Ikramullah v. The State (2015 SCMR 1002), reaffirmed herein, failure to produce the Moharrir or the carrier official breaks the chain of custody.
This fatal break renders the Chemical Examiner's report legally inadmissible and untrustworthy, entitling the accused to an acquittal even if huge quantities of contraband were allegedly seized and the Chemical Examiner's report confirmed narcotic contents.
Appeal filed by the State/ANF dismissed, and acquittal of respondents upheld."""
    },
    {
        "case_id": "2019_SCMR_608",
        "neutral_citation": "2019 SCMR 608",
        "citation": "2019 SCMR 608",
        "case_title": "Abdul Ghani and others v. The State",
        "court_name": "Supreme Court of Pakistan",
        "court": "Supreme Court of Pakistan",
        "year": 2019,
        "decision_date": "2019",
        "statutes": ["Control of Narcotic Substances Act 1997", "Code of Criminal Procedure 1898"],
        "sections": ["Section 9(c)", "Section 51", "Article 185(3)"],
        "full_text": """Citation Name: 2019 SCMR 608 SUPREME-COURT
ABDUL GHANI and others VS THE STATE
Before: Supreme Court of Pakistan
Criminal Appeal No. 13 of 2018, decided on 21st January, 2019.
(On appeal from judgment dated 12-10-2017 of Lahore High Court, Multan Bench)
Present: Asif Saeed Khan Khosa, C.J., Sardar Tariq Masood and Yahya Afridi, JJ.

Control of Narcotic Substances Act (XXV of 1997)---
---Ss. 9(c) & 51---Recovery of 10 kilograms of charas---Safe custody and safe transmission of sample parcels---Unexplained delay in dispatch---Carrier not produced in witness box---Malkhana Register No. 19 not proved---
Held, safe custody of recovered contraband and safe transmission of samples to the Chemical Examiner are sine qua non for establishing an offence under Section 9(c) of CNSA 1997.
Where there is unexplained delay in dispatching samples, and the official who carried and delivered the sample parcels to the Chemical Examiner's laboratory is not examined as a prosecution witness, and no extract from Register No. 19 is placed on record to show that the samples remained in continuous untampered custody in the Malkhana, the chain of custody stands broken.
The Supreme Court held that the prosecution cannot secure a conviction on an assumed transmission of samples; safe transmission must be proved through the sworn testimony of the transmitting official.
The ratio of Ikramullah v. The State (2015 SCMR 1002) and State v. Imam Bakhsh (2018 SCMR 2039) squarely governs the field.
A positive Chemical Examiner report cannot cure the fatal break in safe custody and safe transmission.
Conviction and sentence of life imprisonment under Section 9(c) CNSA 1997 set aside. Appeal allowed, accused acquitted of charges."""
    }
]

async def run_ingestion():
    print("=== Step 1: Upserting Narcotics Apex Precedents into Supabase full_judgments ===")
    for c in NARCOTICS_CASES:
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

    for c in NARCOTICS_CASES:
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
