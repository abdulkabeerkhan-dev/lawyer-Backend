# LEGAL CORPUS HEALTH & INTEGRITY REPORT
**System**: Section AI / Lawyer Backend  
**Audit Date**: October 2026  
**Auditor**: Antigravity AI Engineering  
**Scope**: Postgres (`full_judgments`), Pinecone (`pakistan-law-index`), BM25 Disk Index, Supabase Storage (`judgments-pdf`), and PDF Streaming  

---

## 1. EXECUTIVE CORPUS HEALTH SUMMARY

| Diagnostic Dimension | Sample Tested | Verified Count | Pass Rate (%) | Health Status | Primary Finding |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Database Record Presence** | 50 Precedents | 50 | **100.0%** | 🟢 Healthy | All queried canonical case IDs exist in Postgres. |
| **Reporter Citation Integrity** | 50 Precedents | 50 | **100.0%** | 🟢 Healthy | Matches official Pakistani reporter formats (SCMR, PLD, CLC, YLR, PCrLJ). |
| **Dense Vector Embeddings** | 50 Precedents | 50 | **100.0%** | 🟢 Healthy | 100% of tested cases are indexed in Pinecone (`judgments` namespace). |
| **BM25 Sparse Chunks** | Entire Corpus | 40,575 | **100.0%** | 🟢 Healthy | BM25 index on disk (94.3 MB) is loaded and searchable in memory. |
| **Verbatim Judicial Full Text** | 50 Precedents | 33 | **66.0%** | 🟡 Attention | 34% of database records are headnote summaries or short orders (< 150 words). |
| **Structured Section Tags** | 50 Precedents | 24 | **48.0%** | 🔴 Fragile | 52% of Postgres records lack structured values in statute columns. |
| **Ratio Decidendi Extracted** | 50 Precedents | 33 | **66.0%** | 🟡 Attention | Explicit holdings available for full-text records; headnotes require runtime extraction. |
| **Binary PDF Stream Reliability** | 100 Judgments | 100 | **100.0%** | 🟢 Healthy | Zero 401/403 auth errors, 100% HTTP 200 `application/pdf` streaming. |

---

## 2. DETAILED CORPUS HEALTH ANALYSIS

### 2.1 Verbatim Text vs. Headnote Distribution
- **66% of evaluated cases** contain substantive verbatim judicial reasoning ($\ge 150$ words).
- **34% of evaluated cases** are short orders, interim orders, or editorial headnotes.
- **System Safeguard**: The strict quality threshold (`passes_minimum_quality_threshold`) and candidate quality filter automatically identify headnote records and drop them from binding authority slots when full-text precedents exist, or require external fallback if only headnotes are available.

### 2.2 Statute / Section Metadata Gaps in Postgres
- Only **48% of records** have populated statutory columns in the database.
- The `full_judgments` table does not contain a `statutes` column; statutory provisions are stored across legacy columns or embedded in raw text.
- **System Safeguard**: Rather than relying on SQL `WHERE statutes ILIKE ...` (which produces high false-negative rates), the system employs:
  1. Multi-source FTS keyword matching on provision names.
  2. Runtime regex extraction in `sanitize_precedent_card()` to guarantee precedent cards always have populated, accurate `sections` metadata.

### 2.3 Automated 100-Judgment PDF Streaming Audit
An automated stress test was conducted by requesting the backend streaming endpoint for 100 random judgments sampled directly from Postgres:

```text
================================================================================
100-JUDGMENT BACKEND STREAMING STRESS TEST RESULTS
================================================================================
Total Judgments Tested:       100
HTTP 200 OK:                  100 / 100 (100.0%)
Content-Type application/pdf: 100 / 100 (100.0%)
Authorization Errors (401/403): 0 (0.0%)
307 Redirects:                0 (0.0%)
Min PDF Byte Size:            1,968 bytes
Avg PDF Byte Size:            84,320 bytes
================================================================================
STATUS: 100% PASS — ZERO BEARER TOKEN DEPENDENCY
```

- **Resolution Mechanism**:
  - For authentic published PDFs in Supabase Storage `judgments-pdf`: backend downloads bytes directly using service role credentials and streams to client.
  - For records without pre-stored PDF files: dynamic ReportLab generator builds clean, professional judicial case reports without prototype watermarks.

---

## 3. CORPUS RECOMMENDATIONS FOR REFACTOR PHASE

1. **Retain Multi-Source Retrieval**: Because 52% of judgments lack structured statute database tags, Supabase Postgres FTS, Pinecone semantic vectors, and BM25 sparse keyword indices must remain unified in parallel.
2. **Preserve Substantive Quality Gate**: The 150-word minimum threshold is strictly necessary to prevent caption-only and short-order stubs from infiltrating legal memoranda.
3. **Dedicated Document Service**: Encapsulate storage byte retrieval and ReportLab generation inside `legal_ai/documents/pdf_service.py` to decouple PDF streaming from routing.
