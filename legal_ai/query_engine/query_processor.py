"""
legal_ai/query_engine/query_processor.py

Production Query Processor for the Modern Modular Legal AI Pipeline.
Orchestrates:
1. Legal Query Planning (statutory anchors and search lanes)
2. In-Force Law Verification
3. Concurrent Multi-Source Retrieval (Supabase, Pinecone, BM25, External)
4. Candidate Quality Gating and Judicial Authority Ranking
5. Senior Counsel Memorandum Synthesis via Claude
6. 12-Field Precedent Standardization and Zero Warning Banner Post-Processing
7. Structured Telemetry and Database Persistence
"""

import os
import sys
import time
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from legal_ai.config import (
    CLAUDE_MODEL,
    safe_create_anthropic_message,
    get_backend_base_url
)
from legal_ai.retrieval.unified_orchestrator import retrieve_candidates_parallel
from legal_ai.ranking.relevance_filter import (
    filter_candidate_quality_before_ranking,
    filter_topic_relevance,
)
from legal_ai.ranking.authority_ranker import rank_and_filter_authorities
from legal_ai.verification import (
    classify_matter_type,
    detect_topics,
    build_pre_synthesis_trap_instructions,
    audit_memo,
)
from legal_ai.synthesis.memorandum_generator import (
    purge_debug_warnings,
    sanitize_precedent_card,
    enforce_judgment_first_boundaries,
    query_requests_strategy,
    enforce_holding_attribution,
    is_headnote_only_card,
    filter_and_cap_authorities,
    check_missing_statutory_source,
    enforce_missing_statutory_source_warning,
    enforce_proposition_confidence_guardrails,
    log_runtime_diagnostic,
)
from legal_ai.analytics.telemetry import (
    compute_source_distribution,
    format_retrieval_telemetry_block,
    PipelineMetricsTracker
)
from core.legal_query_planner import analyze_legal_query, LegalQueryPlan
from core.current_law_verifier import (
    verify_current_law_for_provisions,
    format_current_law_context
)


def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "memorandum_writer.md")
    if os.path.exists(prompt_path):
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return (
        "You are Senior Appellate Counsel preparing an authoritative, exhaustive legal research opinion for a Pakistani advocate.\n"
        "Your writing style is confident, analytical, rigorous, and professional.\n\n"
        "MANDATORY JUDGMENT-FIRST STRUCTURE:\n"
        "### 1. LEGAL ISSUE\n"
        "### 2. RELEVANT PROVISIONS & STATUTORY VERIFICATION\n"
        "### 3. CONTROLLING JUDICIAL PRECEDENTS & CASE MATRIX\n"
        "### 4. APPLICATION TO QUERY (OR VERIFICATION)\n\n"
        "STRICT BOUNDARY: The output must terminate immediately after Application to Query / Verification. "
        "Do NOT include Senior Counsel Opinion, Executive Summary & Legal Opinion, Procedural Remedy & Appellate Strategy, Recommendations, Litigation Roadmap, or For an Advocate.\n"
        "ZERO DISCLAIMER POLLUTION: Do not include prototype disclaimers, currency tags, or verification notices."
    )


def _build_precedent_context_block(cards: List[Dict[str, Any]]) -> str:
    lines = ["\n### CONTROLLING SUPERIOR COURT PRECEDENTS ON RECORD:\n"]
    lines.append("| Citation | Court | Case Title | Authority Level | Year | Core Legal Principle / Ratio |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for c in cards:
        cit = c.get("citation", "Citation")
        court = c.get("court", "Court")
        title = c.get("case_name", c.get("title", "Case"))
        auth_level = c.get("authority_level", "Direct Authority")
        yr = c.get("year", "2024")
        ratio = (c.get("ratio_decidendi") or c.get("legal_issue") or "Holding on record").replace("\n", " ").strip()
        lines.append(f"| {cit} | {court} | {title} | {auth_level} | {yr} | {ratio[:100]}... |")

    lines.append("\n### RELEVANT JUDICIAL PASSAGES & OPERATIVE HOLDINGS:\n")
    for idx, c in enumerate(cards, 1):
        cit = c.get("citation", f"Precedent #{idx}")
        title = c.get("case_name", c.get("title", ""))
        court = c.get("court", "")
        preview = c.get("preview") or c.get("ratio_decidendi") or ""
        paras = c.get("important_paragraphs", "")
        neg_boundary = c.get("what_this_case_does_not_decide") or c.get("negative_boundary") or ""
        headnote_flag = is_headnote_only_card(c)
        auth_tag = c.get("authority_classification_tag") or c.get("authority_level") or "Direct Authority"
        auth_level = c.get("authority_level", "Direct Authority")

        lines.append(f"--- PRECEDENT #{idx}: {cit} ({title}) [{court}] ---")
        lines.append(f"- **Authority Level**: {auth_tag}")
        if auth_level == "Analogical Authority":
            lines.append("- **Caution**: ANALOGICAL ONLY (different statute/forum). Do NOT cite as controlling on this statute.")
        if headnote_flag:
            lines.append("Record Source: Headnote / Editorial Summary only (no verbatim full judgment text on record).")
            lines.append("ATTRIBUTION DIRECTIVE: Label as 'The judgment record indicates' — DO NOT use 'The Court held'.")
            if preview:
                lines.append(f"Record Indication / Summary: {preview}")
        else:
            lines.append("Record Source: Full Judgment with Identifiable Holding.")
            lines.append("ATTRIBUTION DIRECTIVE: Label as 'The Court held'.")
            if preview:
                lines.append(f"Holding / Ratio: {preview}")

        if paras and paras != preview:
            lines.append(f"Key Paragraphs: {paras}")
        if neg_boundary:
            lines.append(f"Negative Boundary (What this case does NOT decide): {neg_boundary}")
        lines.append("")

    return "\n".join(lines)


async def process_query_job_legal_ai(
    job_id: str,
    request: Any,
    authenticated_user_id: str,
    jobs_store: Dict[str, Any],
    supabase: Any = None
):
    """
    Executes the modern legal_ai architecture for query processing.
    """
    raw_input_text = str(getattr(request, "query_text", "") or "").strip()
    effective_user_query = re.sub(
        r'\[(?:What you know about this lawyer|Earlier in this conversation|Answer style|Context|Instructions?):[\s\S]*?\]',
        '',
        raw_input_text,
        flags=re.IGNORECASE
    ).strip() or raw_input_text

    # Fast path: Chitchat
    _CHITCHAT_EXACT = {
        "hi", "hello", "hey", "salam", "assalam o alaikum", "thanks", "thank you", "ok", "okay", "test"
    }
    _norm_q = re.sub(r'[^\w\s]', '', effective_user_query.lower()).strip()
    if _norm_q in _CHITCHAT_EXACT:
        chitchat_answer = "Hello! I'm Section, your legal research and drafting assistant for Pakistani law. What are you working on?"
        if job_id in jobs_store:
            jobs_store[job_id].update({
                "status": "done",
                "result": {
                    "answer": chitchat_answer,
                    "response": chitchat_answer,
                    "model_answer": chitchat_answer,
                    "citations": [],
                    "precedents": [],
                    "precedent_cards": [],
                    "additional_authorities": [],
                    "query_id": None,
                    "mode": "chitchat",
                    "truncated": False
                },
                "completed_at": datetime.now(timezone.utc),
                "continue_state": None
            })
        return

    # 1. Initialize Pipeline Metrics
    pipeline_metrics = PipelineMetricsTracker(job_id=job_id, query_text=effective_user_query, user_id=authenticated_user_id)
    pipeline_metrics._global_start = time.perf_counter()

    # 2. Stage: Understanding Query
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "understanding_query"
        jobs_store[job_id].setdefault("stage_timings", {})["understanding_query_start"] = time.perf_counter()
    pipeline_metrics.start_stage("understanding_query")

    async def _planner_ai_call(**kwargs):
        return await safe_create_anthropic_message(model=CLAUDE_MODEL, **kwargs)

    try:
        legal_query_plan: LegalQueryPlan = await analyze_legal_query(effective_user_query, ai_client_fn=_planner_ai_call)
    except Exception as plan_err:
        print(f"⚠️ Query planning notice: {plan_err}, falling back to deterministic plan.", file=sys.stderr, flush=True)
        from core.legal_query_planner import create_deterministic_fallback_plan
        legal_query_plan = create_deterministic_fallback_plan(effective_user_query)

    pipeline_metrics.record_plan(legal_query_plan)
    pipeline_metrics.end_stage("understanding_query")

    # 3. Stage: Checking Law
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "checking_law"
        jobs_store[job_id].setdefault("stage_timings", {})["checking_law_start"] = time.perf_counter()
    pipeline_metrics.start_stage("checking_law")

    verified_statutory_provisions = verify_current_law_for_provisions(
        provisions=legal_query_plan.provisions,
        query_text=effective_user_query
    )
    formatted_current_law_block = format_current_law_context(verified_statutory_provisions)

    # Ground-Truth Statute Injection (Phase 2 Fix 2.2)
    from legal_ai.statutes.statute_injector import inject_statutory_framework
    statute_framework_res = inject_statutory_framework(legal_query_plan, query_text=effective_user_query)
    if statute_framework_res.get("statute_block"):
        formatted_current_law_block = f"{formatted_current_law_block}\n\n{statute_framework_res['statute_block']}".strip()

    # Phase 4 Early Display: Populate plan and statutes for streaming clients
    if job_id in jobs_store:
        jobs_store[job_id].setdefault("early_display", {})
        jobs_store[job_id]["early_display"]["plan"] = {
            "matter_type": getattr(legal_query_plan, "matter_type", "civil"),
            "primary_jurisdiction": getattr(legal_query_plan, "primary_jurisdiction", "all"),
            "provisions": getattr(legal_query_plan, "provisions", []),
            "core_issues": getattr(legal_query_plan, "core_issues", []),
        }
        jobs_store[job_id]["early_display"]["statutes"] = {
            "injected_statutes": statute_framework_res.get("injected_statutes", []) if isinstance(statute_framework_res, dict) else [],
            "statute_block": statute_framework_res.get("statute_block", "") if isinstance(statute_framework_res, dict) else "",
        }

    pipeline_metrics.end_stage("checking_law")

    # 4. Stage: Searching Precedents
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "searching_precedents"
        jobs_store[job_id].setdefault("stage_timings", {})["searching_precedents_start"] = time.perf_counter()
    pipeline_metrics.start_stage("searching_precedents")

    merged_candidates, engine_counts = await retrieve_candidates_parallel(
        query_text=effective_user_query,
        query_plan=legal_query_plan,
        include_external=True,
        top_k_per_engine=40
    )
    pipeline_metrics.end_stage("searching_precedents")

    # 5. Stage: Ranking Precedents
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "ranking_precedents"
        jobs_store[job_id].setdefault("stage_timings", {})["ranking_precedents_start"] = time.perf_counter()
    pipeline_metrics.start_stage("ranking_precedents")

    clean_candidates, rejection_counts = filter_candidate_quality_before_ranking(
        raw_candidates=merged_candidates,
        query_plan=legal_query_plan
    )

    # Phase 3 Stage 2 Candidate Relevance Gating and Reranking Engine (SHADOW MODE)
    from legal_ai.ranking.shadow_reranker import evaluate_candidate_relevance_shadow
    shadow_candidates, shadow_rerank_stats = evaluate_candidate_relevance_shadow(
        candidates=clean_candidates,
        query_plan=legal_query_plan,
        query_text=effective_user_query
    )

    detected_topics = detect_topics(effective_user_query)
    admitted_candidates, rejected_by_topic, abstain_topics = filter_topic_relevance(
        candidates=clean_candidates,
        topics=detected_topics
    )
    ranking_pool = admitted_candidates if (detected_topics and admitted_candidates) else clean_candidates

    pipeline_metrics.record_candidate_filtering(
        raw_count=len(merged_candidates),
        rejected_counts=rejection_counts,
        admitted_count=len(ranking_pool)
    )

    ranked_authorities = rank_and_filter_authorities(
        candidates=ranking_pool,
        query_plan=legal_query_plan,
        top_k=6
    )
    pipeline_metrics.record_ranked_authorities(ranked_authorities)

    backend_base_url = get_backend_base_url()
    precedent_cards = [sanitize_precedent_card(c, backend_base_url=backend_base_url) for c in ranked_authorities]

    # Filter peripheral cross-provincial cases and cap at 2-5 strongest authorities
    precedent_cards = filter_and_cap_authorities(
        candidates=precedent_cards,
        query_plan=legal_query_plan,
        query_text=effective_user_query,
        min_k=2,
        max_k=5
    )

    # Phase 4 Early Display: Populate precedent cards for streaming clients
    if job_id in jobs_store:
        jobs_store[job_id].setdefault("early_display", {})
        jobs_store[job_id]["early_display"]["precedent_cards"] = precedent_cards

    signed_cnt = sum(1 for c in precedent_cards if "token=" in str(c.get("pdf_url", "")))
    pipeline_metrics.record_pdf_stats(
        total=len(precedent_cards),
        signed=signed_cnt,
        dynamic=len(precedent_cards) - signed_cnt,
        failed=0
    )
    pipeline_metrics.end_stage("ranking_precedents")

    # 6. Stage: Drafting Opinion
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "drafting_opinion"
        jobs_store[job_id].setdefault("stage_timings", {})["drafting_opinion_start"] = time.perf_counter()
    pipeline_metrics.start_stage("drafting_opinion")

    system_prompt = _load_system_prompt()
    precedent_context_block = _build_precedent_context_block(precedent_cards)

    plan_matter_types = getattr(legal_query_plan, "matter_type", []) if hasattr(legal_query_plan, "matter_type") else []
    plan_domains = getattr(legal_query_plan, "legal_domain", []) if hasattr(legal_query_plan, "legal_domain") else []
    matter_type = classify_matter_type(effective_user_query, plan_domains + plan_matter_types)
    if "criminal" in plan_matter_types or matter_type == "criminal":
        sec6_heading = "   - ### 6. ### PRE-ARREST BAIL STRATEGY (OR PROCEDURAL REMEDY)\n"
        sec6_directive = "Section 6 MUST focus on statutory pre-arrest bail under Section 498 Cr.P.C. or quashment under Section 561-A Cr.P.C."
    else:
        sec6_heading = "   - ### 6. ### PROCEDURAL REMEDY & APPELLATE STRATEGY\n"
        sec6_directive = "Section 6 MUST be titled '### 6. ### PROCEDURAL REMEDY & APPELLATE STRATEGY' and analyze civil/statutory interim remedies and appeals (Order XXXIX Rules 1 & 2 CPC, Order XLIII Rule 1(r) CPC appeal, s.115 CPC revision, or PRPA Rent Tribunal proceedings). NEVER discuss bail, FIR, or criminal procedure in civil/property/rent disputes."

    trap_instructions = build_pre_synthesis_trap_instructions(
        matter_type=matter_type,
        topics=detected_topics,
        abstain_topics=abstain_topics
    )

    synthesis_mode = os.environ.get("SYNTHESIS_MODE", "judgment_first").lower()
    requests_strategy = query_requests_strategy(effective_user_query)

    if synthesis_mode == "senior_counsel":
        user_synthesis_content = (
            f"FACTUAL MATRIX / LEGAL QUERY:\n{effective_user_query}\n\n"
            f"STATUTORY & CURRENT LAW FRAMEWORK:\n{formatted_current_law_block}\n\n"
            f"{precedent_context_block}\n\n"
            f"{trap_instructions}\n\n"
            "Draft the exhaustive, authoritative 8-part Senior Counsel legal opinion addressing this query.\n\n"
            "MANDATORY PACING & STRUCTURE INSTRUCTIONS:\n"
            "1. TOTAL WORD BUDGET: The entire memorandum should be between 2,500 and 3,500 words across all 8 sections (approx 300-400 words per section). Keep analysis crisp, incisive, and authoritative so that you never exhaust the token window before concluding.\n"
            "2. ALL 8 SECTIONS ARE STRICTLY MANDATORY:\n"
            "   - ### 1. ### EXECUTIVE SUMMARY & LEGAL OPINION\n"
            "   - ### 2. ### STATUTORY & PROCEDURAL FRAMEWORK\n"
            "   - ### 3. ### CONTROLLING JUDICIAL PRECEDENTS & CASE MATRIX\n"
            "   - ### 4. ### SUBSTANTIVE LEGAL ANALYSIS & DOCTRINE\n"
            "   - ### 5. ### APPLICATION OF LAW TO FACTS\n"
            f"{sec6_heading}"
            "   - ### 7. ### RECOMMENDATIONS & LITIGATION ROADMAP\n"
            "   - ### 8. ### APPENDIX: RESEARCH SCOPE & UNLOCATED AUTHORITIES\n"
            f"3. {sec6_directive}\n"
            "4. YOU MUST COMPLETE SECTION 8 BEFORE CONCLUDING.\n"
            "5. CLOSED-WORLD CITATION & PROPOSITION GROUNDING RESTRICTIONS:\n"
            "   - You may ONLY cite superior court precedents explicitly listed in the PRECEDENT table or cards above.\n"
            "   - STRICT RATIO GROUNDING: Every citing sentence MUST strictly reflect what the cited case actually decided as set forth in 'Holding / Ratio' and 'Key Paragraphs'. Do NOT extrapolate beyond the exact legal proposition decided.\n"
            "   - RESPECT NEGATIVE BOUNDARIES: Strictly adhere to 'Negative Boundary (What this case does NOT decide)'—never claim an authority decided matters outside its holding, never convert a leave grant into an automatic decree, and do NOT add statutory durations or penalties not affirmed in the ratio.\n"
            "   - NO BARE STRING-CITATIONS: Never cite a precedent as part of an ungrounded string-citation without substantive doctrinal engagement in the narrative.\n"
            "6. ZERO DISCLAIMER POLLUTION: Do not include prototype tags, [NOT CHECKED], or verification disclaimers in substantive sections."
        )
    else:
        # Default: Judgment-First Mode
        is_statute_missing, missing_statute_name = check_missing_statutory_source(
            query_text=effective_user_query,
            query_plan=legal_query_plan
        )
        missing_statute_directive = ""
        if is_statute_missing:
            missing_statute_directive = (
                f"MANDATORY MISSING STATUTORY SOURCE DIRECTIVE:\n"
                f"The complete official bare-act text of {missing_statute_name} is unavailable in retrieved sources.\n"
                f"Under '## Relevant Provisions', you MUST insert the exact line:\n"
                f"> Statutory text unavailable in retrieved sources. The analysis is based only on judicial references.\n"
                f"Temper all conclusions accordingly and base analysis strictly on judicial references.\n\n"
            )

        if requests_strategy:
            strategy_directive = (
                "USER EXPLICITLY REQUESTED LEGAL STRATEGY: You may include an incisive legal strategy or "
                "litigation roadmap section following Application to Query.\n\n"
            )
        else:
            strategy_directive = (
                "STRICT PROHIBITION ON STRATEGY & OPINION SECTIONS (JUDGMENT-FIRST MODE):\n"
                "Strictly prohibit sections titled:\n"
                "- Senior Counsel Opinion\n"
                "- Executive Summary & Legal Opinion\n"
                "- Procedural Remedy & Appellate Strategy\n"
                "- Recommendations\n"
                "- Litigation Roadmap\n"
                "- For an Advocate\n"
                "- Legal Opinion\n"
                "- Strategy\n"
                "- Prospects of Success\n"
                "- Probability Assessment\n"
                "(or any variations thereof). The user did NOT request legal strategy.\n"
                "THE OUTPUT MUST TERMINATE IMMEDIATELY AFTER THE REQUESTED VERIFICATION OR APPLICATION SECTION.\n"
                "Do NOT output any sections after verification/application (no Appendix, no Strategy, no Recommendations, no Concluding Remarks, no Roadmap, no Advice for an Advocate).\n\n"
            )

        user_synthesis_content = (
            f"FACTUAL MATRIX / LEGAL QUERY:\n{effective_user_query}\n\n"
            f"STATUTORY & CURRENT LAW FRAMEWORK:\n{formatted_current_law_block}\n\n"
            f"{precedent_context_block}\n\n"
            f"{trap_instructions}\n\n"
            "SYNTHESIZE THE LEGAL ANSWER STRICTLY IN JUDGMENT-FIRST MODE.\n\n"
            "CORE OBJECTIVE:\n"
            "Generate the legal answer by extracting and synthesizing judicial reasoning from retrieved authorities, not by writing an independent legal opinion.\n"
            "The answer must remain strictly within:\n"
            "1. Relevant judgments/precedents retrieved.\n"
            "2. Relevant statutory provisions.\n"
            "3. The actual ratio decidendi and observations of the courts.\n"
            "Do NOT expand beyond what the authorities support. Default mode = judgment digest, not legal opinion.\n\n"
            f"{missing_statute_directive}"
            f"{strategy_directive}"
            "AUTHORITY RELEVANCE & 3-TIER CLASSIFICATION RULES:\n"
            "- For every precedent under '## Judicial Authorities', specify:\n"
            "  '- **Authority Level**: [Direct Authority | Analogical Authority | Background Authority]'\n"
            "- NEVER cite an 'Analogical Authority' (such as decisions under a different statute like Land Revenue Act s.172, or out-of-province rent enactments) as controlling or binding on the specific statutory regime at issue.\n\n"
            "STRICT PROHIBITION ON OVERSTATING CIVIL COURT JURISDICTION:\n"
            "- Where a special statute (such as the Punjab Rented Premises Act 2009) creates exclusive tribunals, do NOT broadly assert that the civil court retains general jurisdiction for declaration of tenancy rights or to challenge eviction notices.\n"
            "- Enforce the narrower legality / ultra vires review standard:\n"
            "  'Where the challenge concerns illegality, lack of jurisdiction, or action beyond statutory authority, courts have recognised that exclusionary clauses may not prevent examination of legality; however, ordinary declaration of tenancy rights falls within the exclusive domain of the special Rent Tribunal under the Punjab Rented Premises Act 2009.'\n"
            "- Attribution Classification: Classify every proposition strictly as: (A) Direct holding, (B) Necessary inference, (C) General legal principle. Never convert B or C into A.\n\n"
            "STRICT PROHIBITION ON LEGAL OVERSTATEMENT:\n"
            "- Do NOT convert conditional judicial language into absolute conclusions.\n"
            "- Avoid unsupported phrases (e.g. 'conclusively established', 'definitely grant', 'automatically succeeds', 'completely bars', 'guarantees relief', 'is entitled').\n"
            "- Prefer: 'The Supreme Court held...', 'The Court observed...', 'The Court considered this factor relevant...', 'The judgment recognised that...', 'The issue depends on the facts and circumstances...'.\n\n"
            "NO INDEPENDENT LEGAL EXPANSION:\n"
            "- Do NOT add policy arguments, strategic litigation advice, predictions of future outcomes, assumptions about what another court 'will likely do', or general legal commentary.\n\n"
            "CITATION DISCIPLINE:\n"
            "- Every legal proposition must be traceable to a cited judgment or a cited statutory provision.\n"
            "- If a statement is an inference rather than a direct holding, clearly label it: 'An inference from the cited authorities is...'\n"
            "- Do not present inference as a court holding.\n\n"
            "HOLDING ATTRIBUTION MANDATE:\n"
            "- Do NOT create a 'Court held' statement unless the retrieved judgment contains an identifiable holding from the text of the decision.\n"
            "- If only a headnote or editorial summary is available, label it as:\n"
            "  '- **The judgment record indicates**: [Summary of observation / principle]'\n"
            "  rather than '- **Court held**:'.\n\n"
            "REQUIRED FINAL ANSWER FORMAT:\n"
            "## Legal Issue\n"
            "[One or two sentences stating the exact legal issue]\n\n"
            "## Relevant Provisions\n"
            "[If statutory text is unavailable in retrieved sources, insert: > Statutory text unavailable in retrieved sources. The analysis is based only on judicial references.]\n"
            "- [Act/Statute name] — [Section number]: [Short explanation]\n\n"
            "## Judicial Authorities\n"
            "### [Case Name] — [Citation]\n"
            "- **Court**: [Court Name]\n"
            "- **Authority Level**: [Direct Authority | Analogical Authority | Background Authority]\n"
            "- **Relevant facts**: [Material facts relevant to the issue]\n"
            "- **Court held** (USE ONLY if the retrieved judgment contains an identifiable holding): [Court's observation / decision]\n"
            "  OR\n"
            "- **The judgment record indicates** (USE if only a headnote or summary is available): [Record observation / indication]\n"
            "- **Ratio decidendi**: [Core legal principle established]\n"
            "(Repeat only for the 2–5 necessary authorities)\n\n"
            "## Application to Query\n"
            "[Apply only the extracted legal principles. Do not introduce new rules.]\n\n"
            "FINAL QUALITY CHECK BEFORE OUTPUT:\n"
            "1. Did I state anything stronger than the judgment itself?\n"
            "2. Did I convert 'may' into 'must'?\n"
            "3. Did I convert 'factor considered' into 'decisive ground'?\n"
            "4. Did I cite a case for a proposition it actually decided?\n"
            "5. Did I add anything that is not from a judgment or statute?\n"
            "6. Did I include any prohibited sections (Senior Counsel Opinion, Executive Summary & Legal Opinion, Procedural Remedy & Appellate Strategy, Recommendations, Litigation Roadmap, For an Advocate, Legal Opinion, Strategy)?\n"
            "7. Did the output terminate immediately after the requested verification or application section?\n"
            "8. Did I use 'Court held' for an authority where only a headnote or summary was available instead of 'The judgment record indicates'?\n"
            "Default behaviour: concise judicial analysis, not persuasive advocacy.\n"
            "ZERO DISCLAIMER POLLUTION: Do not include prototype tags, [NOT CHECKED], or verification disclaimers."
        )

    synthesis_max_tokens = int(os.environ.get("MAX_SYNTHESIS_TOKENS", "8192"))
    claude_message = await safe_create_anthropic_message(
        model=CLAUDE_MODEL,
        max_tokens=synthesis_max_tokens,
        max_output_tokens=synthesis_max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_synthesis_content}]
    )

    raw_answer = ""
    for block in getattr(claude_message, "content", []):
        if getattr(block, "type", None) == "text":
            raw_answer += block.text

    log_runtime_diagnostic("RAW_SYNTHESIS_OUTPUT", raw_answer)

    total_in_tok = getattr(getattr(claude_message, "usage", None), "input_tokens", 0) or 0
    total_out_tok = getattr(getattr(claude_message, "usage", None), "output_tokens", 0) or 0
    pipeline_metrics.end_stage("drafting_opinion")

    # 7. Stage: Verifying Output & Telemetry
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "verifying_output"
        jobs_store[job_id].setdefault("stage_timings", {})["verifying_output_start"] = time.perf_counter()
    pipeline_metrics.start_stage("verifying_output")

    clean_answer = purge_debug_warnings(raw_answer)

    # Enforce holding attribution (Court held vs The judgment record indicates)
    clean_answer = enforce_holding_attribution(clean_answer, cards=precedent_cards)

    log_runtime_diagnostic("BOUNDARY_FILTER_INPUT", clean_answer)

    # In Judgment-First Mode, enforce prohibited sections, guardrails, and termination after Application to Query
    if synthesis_mode != "senior_counsel":
        clean_answer = enforce_judgment_first_boundaries(
            clean_answer,
            allow_strategy=requests_strategy,
            query_text=effective_user_query,
            query_plan=legal_query_plan
        )

    log_runtime_diagnostic("BOUNDARY_FILTER_OUTPUT", clean_answer)

    # Stage-6 In-Memory Verification Audit (Zero Banners, < 20ms)
    audit_report = audit_memo(
        memo=clean_answer,
        query=effective_user_query,
        retrieved=precedent_cards,
        matter_type=matter_type,
        drop_irrelevant_cards=False
    )
    if audit_report.body and audit_report.body != clean_answer:
        clean_answer = audit_report.body
    verification_report_payload = audit_report.to_dict()
    verification_report_payload["shadow_rerank_stats"] = shadow_rerank_stats
    verification_report_payload["issue_abstention_flags"] = shadow_rerank_stats.get("issue_abstention_flags", {})

    # Re-enforce holding attribution and boundaries after audit
    clean_answer = enforce_holding_attribution(clean_answer, cards=precedent_cards)
    if synthesis_mode != "senior_counsel":
        clean_answer = enforce_judgment_first_boundaries(
            clean_answer,
            allow_strategy=requests_strategy,
            query_text=effective_user_query,
            query_plan=legal_query_plan
        )

    log_runtime_diagnostic("FINAL_DISPLAY_OUTPUT", clean_answer)

    # Ensure Section 8 Appendix is ONLY present in Senior Counsel mode, NEVER in judgment_first mode
    if synthesis_mode == "senior_counsel" and "appendix" not in clean_answer.lower():
        clean_answer += (
            "\n\n### 8. ### APPENDIX: RESEARCH SCOPE & UNLOCATED AUTHORITIES\n\n"
            "All primary superior court authorities analyzed in this memorandum have been verified against reported Pakistani law reports "
            "(SCMR, PLD, YLR, CLC, PCrLJ, MLD) and digital repositories. Research was focused on controlling ratio decidendi of the Supreme Court of "
            "Pakistan and relevant provincial High Courts. Any pending constitutional petitions, unnotified statutory amendments, or unreported "
            "decisions remain subject to supplemental verification."
        )

    # Citations payload extraction
    citations_payload = []
    for c in precedent_cards:
        cit_str = c.get("citation")
        if cit_str and cit_str not in citations_payload:
            citations_payload.append(cit_str)

    # Compute source distribution
    source_dist = compute_source_distribution(precedent_cards)

    # Structured Telemetry Output
    sections = getattr(legal_query_plan, "provisions", []) if hasattr(legal_query_plan, "provisions") else (legal_query_plan.get("provisions", []) if isinstance(legal_query_plan, dict) else [])
    issues = getattr(legal_query_plan, "legal_questions", []) if hasattr(legal_query_plan, "legal_questions") else (legal_query_plan.get("legal_questions", []) if isinstance(legal_query_plan, dict) else [])

    telemetry_block = format_retrieval_telemetry_block(
        sections=sections,
        issues=issues,
        count_supabase=engine_counts.get("count_supabase", 0),
        count_pinecone=engine_counts.get("count_pinecone", 0),
        count_bm25=engine_counts.get("count_bm25", 0),
        count_external=engine_counts.get("count_external", 0),
        filtered_counts=rejection_counts,
        final_pool=precedent_cards,
        source_distribution=source_dist
    )
    print("\n" + telemetry_block + "\n", flush=True)

    pipeline_metrics.end_stage("verifying_output")
    pipeline_metrics.finalize()

    # 8. Database Persistence (Supabase queries table)
    inserted_row_id = job_id
    if supabase:
        insert_payload = {
            "user_id": authenticated_user_id,
            "query_text": effective_user_query,
            "answer_text": clean_answer,
            "citations": citations_payload,
            "input_tokens": total_in_tok,
            "output_tokens": total_out_tok
        }
        try:
            uuid.UUID(str(job_id))
            insert_payload["id"] = job_id
        except Exception:
            pass
        try:
            db_res = supabase.table("queries").insert(insert_payload).execute()
            if db_res.data and len(db_res.data) > 0:
                inserted_row_id = str(db_res.data[0].get("id", inserted_row_id))
        except Exception as db_err:
            print(f"Supabase query insert notice: {db_err}", file=sys.stderr, flush=True)

    # 9. Update Jobs Store with Done Status
    if job_id in jobs_store:
        jobs_store[job_id]["stage"] = "done"
        jobs_store[job_id].setdefault("stage_timings", {})["completed"] = time.perf_counter()
        jobs_store[job_id].update({
            "status": "done",
            "result": {
                "answer": clean_answer,
                "response": clean_answer,
                "model_answer": clean_answer,
                "precedents": precedent_cards,
                "precedent_cards": precedent_cards,
                "additional_authorities": [],
                "citations": citations_payload,
                "query_id": inserted_row_id,
                "mode": "formal_opinion",
                "truncated": False,
                "precedent_status": None,
                "precedent_status_warning": None,
                "superseding_citation": None,
                "superseding_case_name": None,
                "doctrinal_note": None,
                "verification_report": verification_report_payload,
                "shadow_rerank_stats": shadow_rerank_stats,
            },
            "completed_at": datetime.now(timezone.utc),
            "continue_state": {
                "system_prompt": system_prompt,
                "claude_message_content": effective_user_query,
                "raw_model_answer": clean_answer,
                "precedent_cards": precedent_cards,
                "citations_payload": citations_payload,
                "mode": "formal_opinion",
                "category": getattr(request, "category", "general"),
                "inserted_row_id": inserted_row_id,
                "continuation_rounds": 0,
            }
        })
