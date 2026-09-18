# Section retrieval eval suite

Adapted from Lawglance's `eval/` framework (Apache 2.0 — MIT/attribution-safe
to reuse). Two kinds of check, scored separately:

1. **Findability** — for queries where real case law exists, does retrieval
   actually surface the right citation, and how high does it rank? Scored
   with recall + MRR (mean reciprocal rank), same as Lawglance.
2. **Refusal** — for queries where NO real precedent should be groundable
   (e.g. the Section 9 CPC eviction case), does retrieval correctly return
   zero candidates instead of quietly falling back to weak matches? This is
   the check Lawglance doesn't need but Section does — it's what would have
   caught the `FALLBACK_FLOOR` regression automatically.

## Files

- `golden_set.py` — the `GoldenQAItem` model + loader/saver. Matches on
  `citation`, not raw chunk text (unlike Lawglance) — citations are stable
  across re-chunking, chunk text isn't.
- `metrics.py` — recall, MRR, Wilson confidence interval (from Lawglance),
  plus `refusal_accuracy` (new, for the should-refuse items).
- `golden_qa.json` — the actual test cases. Currently seeded with 3 items
  from this debugging session. **Add to this every time a real bug turns up**
  — that's how it becomes a real regression net instead of a one-time report.
- `golden_qa_pending.md` — items flagged as possible gaps but not yet
  confirmed enough to score against. Move into `golden_qa.json` once verified.
- `retrieval_eval.py` — runs the golden set against the real
  `LegalSearchPipeline.search_precedents()` in `main.py` (real Pinecone +
  Voyage calls, not mocked) and prints a pass/fail report.

## Running it

1. Make sure your `.env` has `PINECONE_API_KEY`, `VOYAGE_API_KEY`, and `PINECONE_INDEX_NAME` set.
2. From the backend root:
   ```
   python -m eval.retrieval_eval
   ```
3. A 🚨 on any refusal check means something is now grounding an answer that
   shouldn't be grounded — treat that as a blocking bug, not a warning.

## Growing the set

Every time you or the agent hand-verify a query during debugging (the way
we did for khula, the bail question, and the CPC eviction case), turn it
into a golden set row instead of letting it disappear at the end of the
conversation. That's the only thing that makes this a regression suite
instead of a one-off audit.
