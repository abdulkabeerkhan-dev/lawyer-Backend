# Section Legal AI Engine - Technical Roadmap

## Phase 1–5: Core Engine Foundations (Completed)
- [x] High-precision legal query planning and multi-lane retrieval (Voyage AI + Pinecone + Turso FTS5).
- [x] Complete Pakistan Statutes Knowledge Base: 620,084 unique statutory provisions ingested into local SQLite and Turso cloud database across all 5 jurisdictions (Federal, Punjab, Sindh, KPK, Balochistan).
- [x] Plain-code deterministic verifier (Layer 7) checking verbatim statutory quotes, article vs section units, and evidence tags.
- [x] Real-time limitation calculator for Article 113, Article 57, Order XXXVII CPC, and alternative remedies.
- [x] Honest failure reporting: strict gating of claims, prohibition of fabricated citations, and removal of ungrounded holdings.

## Phase 6: Production Hardening & Cloud Infrastructure (Completed)
- [x] Zero-downtime microservices deployment on Railway (`lawyer-backend` and `section-frontend`).
- [x] Dynamic HMAC token generation for secured judicial PDF streaming (`/judgment-pdf/{case_id}`).
- [x] Multi-database synchronization: local master FTS5 database (`pakistan_statutes_master.db`) and Turso cloud pipeline.

## Phase 7: Full Judgment Text Bulk Ingestion & High-Fidelity OCR Pipeline (Active Priority)
- [ ] **Full Text Corpus Scaling**: Scale beyond the current 141,481 full judgments in Turso DB to achieve 100% full-text coverage of all historical and contemporary Pakistani law reporters:
  - Supreme Court Reports: *PLD (SC)*, *SCMR*, *PSC*.
  - High Court Reporters: *PLD*, *MLD*, *CLC*, *YLR*, *LHC*.
  - Specialized Tribunals: *PCrLJ* (Criminal), *PTD* (Tax), *PLC* (Labour/Service).
- [ ] **Automated Court Gazette & Physical Reporter Ingestion**:
  - High-throughput PDF extraction and OCR processing pipeline with Tesseract / PaddleOCR for scanned historical gazettes.
  - Structural layout analysis: automatic boundary detection separating headnote, editorial syllabus, appearances, facts, and judicial opinions (*ratio decidendi* vs *obiter dicta*).
- [ ] **Deterministic Verification Gating**:
  - 4-word shingle overlap ($\ge 0.35$) against verified full text to validate precedent citations.
  - Records lacking authenticated full text strictly marked `HEADNOTE_ONLY - not verified`.
  - Strict UI badge blocking: the "Verified Source" / "Verified Judicial Text" badge is gated exclusively on full text presence.
