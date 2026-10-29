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



    verify_and_scrub_memo_claims,



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



        "ACCURACY: Ensure all statements are strictly grounded in retrieved sources."



    )











def _build_precedent_context_block(cards: List[Dict[str, Any]]) -> str:



    from core.legal_guardrails import derive_court_from_judgment_header







    lines = ["\n### CONTROLLING SUPERIOR COURT PRECEDENTS ON RECORD:\n"]



    lines.append("| Citation | Court | Case Title | Authority Level | Year | Core Legal Principle / Ratio |")



    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")



    for c in cards:



        cit = c.get("citation", "Citation")



        title = c.get("case_name", c.get("title", "Case"))



        raw_court = c.get("court", "Court")



        court = derive_court_from_judgment_header(f"{title} {c.get('text', '')}", raw_court)

        c["court"] = court



        auth_level = c.get("authority_level", "Direct Authority")



        yr = c.get("year", "2024")



        ratio = (c.get("ratio_decidendi") or c.get("legal_issue") or "Holding on record").replace("\n", " ").strip()



        lines.append(f"| {cit} | {court} | {title} | {auth_level} | {yr} | {ratio[:100]}... |")







    lines.append("\n### RELEVANT JUDICIAL PASSAGES & OPERATIVE HOLDINGS:\n")



    for idx, c in enumerate(cards, 1):



        cit = c.get("citation", f"Precedent #{idx}")



        title = c.get("case_name", c.get("title", ""))



        raw_court = c.get("court", "")



        court = derive_court_from_judgment_header(f"{title} {c.get('text', '')}", raw_court)



        preview = c.get("preview") or c.get("ratio_decidendi") or ""



        paras = c.get("important_paragraphs", "")



        neg_boundary = c.get("what_this_case_does_not_decide") or c.get("negative_boundary") or ""



        headnote_flag = is_headnote_only_card(c)



        auth_tag = c.get("authority_classification_tag") or c.get("authority_level") or "Direct Authority"



        auth_level = c.get("authority_level", "Direct Authority")







        lines.append(f"--- PRECEDENT #{idx}: {cit} ({title}) [{court}] ---")



        lines.append(f"- **Court**: {court}")



        lines.append(f"- **Authority Level**: {auth_tag}")



        if auth_level == "Analogical Authority":



            lines.append("- **Caution**: ANALOGICAL ONLY (different statute/forum). Do NOT cite as controlling on this statute.")



        



        # Check if record is a machine summary or partial excerpt



        has_full_judgment = bool(c.get("raw_judgment_text")) and len(c.get("raw_judgment_text", "")) > 1500



        if not has_full_judgment or headnote_flag:



            lines.append("- **Record Source**: Partial excerpt / machine summary (unverified against official law report).")



            lines.append("- **Attribution Directive**: Label strictly as '- **The judgment record indicates (machine summary, unverified)**: ...' -- DO NOT use '- **Court held**:' and DO NOT claim an unverified ratio decidendi.")



        else:



            lines.append("- **Record Source**: Full judgment on record.")



            lines.append("- **Attribution Directive**: You may cite direct holdings only if supported by the verbatim text.")







        if preview:



            lines.append(f"Extracted Excerpt / Indication: {preview}")



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



    raw_input_text = str(getattr(request, "query_text", "") or getattr(request, "query", "") or "").strip()



    effective_user_query = re.sub(



        r'\[(?:What you know about this lawyer|Earlier in this conversation|Answer style|Context|Instructions?):[\s\S]*?\]',



        '',



        raw_input_text,



        flags=re.IGNORECASE



    ).strip() or raw_input_text







        # Multi-turn conversation context resolution
    messages_list = getattr(request, "messages", None) or []
    if isinstance(messages_list, list) and len(messages_list) > 0:
        prior_context_parts = []
        for m in messages_list:
            m_role = (m.get("role") if isinstance(m, dict) else getattr(m, "role", "user")) or "user"
            m_content = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")) or ""
            m_content = m_content.strip()
            if not m_content:
                continue
            if m_role == "user" and m_content != raw_input_text:
                prior_context_parts.append(f"Prior User Query: {m_content}")
            elif m_role == "assistant":
                m_match = re.search(r'## Primary Legal Finding\s*\n+([^\n]+(?:\n[^\n]+)?)', m_content)
                if m_match:
                    prior_context_parts.append(f"Prior Finding: {m_match.group(1).strip()[:300]}")
                else:
                    first_p = m_content.split("\n\n")[0].strip()
                    if first_p and not first_p.startswith(">") and len(first_p) < 400:
                        prior_context_parts.append(f"Prior Context: {first_p}")

        lower_q = effective_user_query.lower()
        is_follow_up = False
        follow_up_cues = ["this", "that", "it", "these", "those", "how to present", "how to argue", "court", "pleading", "application", "what next", "explain further", "how should"]
        if prior_context_parts:
            if len(effective_user_query.split()) < 25 or any(cue in lower_q for cue in follow_up_cues):
                is_follow_up = True

        if is_follow_up and prior_context_parts:
            effective_user_query = f"{' | '.join(prior_context_parts[-2:])}\n\nFollow-up Request: {effective_user_query}"

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







    # Early detection of impossible or synthetic citations (e.g. page > 3000)
    # ORDER 2.1 - ITEM 2: Never extract case titles from user query; only inspect real report citations
    try:
        from legal_ai.verification.memo_verifier import MemoVerifier, MemorandumVerificationBlockedError
        _early_mv = MemoVerifier()
        _early_auths = [a for a in _early_mv.extract_case_authorities(effective_user_query) if a.get("type") == "citation"]
        _impossible_cits = []
        _unverified_cits = []
        for _qa in _early_auths:
            _sp = _qa.get("span", "")
            _parts = _sp.split()
            if _parts and _parts[-1].isdigit():
                if int(_parts[-1]) > 3000:
                    _impossible_cits.append(_sp)
            if not _early_mv.verify_case_authority(_qa):
                _unverified_cits.append(_sp)
        
        if _impossible_cits:
            _cit_disp = ", ".join(f"`{c}`" for c in _unverified_cits) if _unverified_cits else ", ".join(f"`{c}`" for c in _impossible_cits)
            _early_blocked_payload = {
                'status': 'error',
                'stage': 'verification_blocked',
                'error': 'MEMORANDUM_VERIFICATION_FAILED',
                'error_category': 'FABRICATED_CITATION',
                'safe_reason': (
                    f"The requested citation {_cit_disp} contains out-of-range volume pagination (> 3,000 pages) "
                    f"and does not exist in authentic Pakistani law reports (SCMR, PLD, CLD, CLC, PCrLJ, MLD, PTD, PLC)."
                ),
                'retry_guidance': (
                    f"Please verify the citation journal, publication year, and page number for {_cit_disp}. "
                    f"In Pakistan, annual volume pagination for law journals rarely exceeds 2,000–2,500 pages."
                ),
                'unverified_citations': _unverified_cits or _impossible_cits,
                'query_text': effective_user_query,
                'verified_statute_fallback': [],
                'verified_precedents_fallback': [],
                'precedent_cards': [],
                'attempts': [],
                'early_display': None,
                'result': None,
                'verification_report': {
                    'verdict': 'BLOCKED',
                    'total_failures': len(_impossible_cits),
                    'failures': [
                        {
                            'rule': '(c)',
                            'category': 'UNVERIFIED_AUTHORITY',
                            'label': 'UNVERIFIED AUTHORITY (not found in our index; check manually)',
                            'issue': f"Citation '{c}' has impossible volume page number exceeding authentic law report publications.",
                            'span': c
                        }
                        for c in _impossible_cits
                    ]
                },
                'completed_at': datetime.now(timezone.utc),
            }
            if job_id in jobs_store:
                jobs_store[job_id].update(_early_blocked_payload)
            raise MemorandumVerificationBlockedError(_early_blocked_payload['verification_report'], blocked_payload=_early_blocked_payload)
    except MemorandumVerificationBlockedError:
        raise
    except Exception as early_err:
        print(f"⚠️ [JOB {job_id}] Early citation guard notice: {early_err}", file=sys.stderr, flush=True)

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

    # STAGE 1, 2 & 3: DUAL TRACK STATUTE ROUTING & CONSENSUS VOTING
    from legal_ai.query_engine.consensus_engine import ConsensusVotingEngine
    consensus_engine = ConsensusVotingEngine(ai_client_fn=_planner_ai_call)
    try:
        consensus_data = await consensus_engine.execute_consensus_pipeline(
            query=effective_user_query,
            provisions_from_plan=legal_query_plan.provisions
        )
        verified_claims = consensus_data.get("verified_provisions", [])
        if verified_claims:
            for vc in verified_claims:
                p_str = vc["provision"]
                if p_str not in legal_query_plan.provisions:
                    legal_query_plan.provisions.append(p_str)
        consensus_grounded_block = consensus_engine.assemble_grounded_synthesis_block(consensus_data.get("consensus", {}))
        if consensus_grounded_block:
            formatted_current_law_block = f"{formatted_current_law_block}\n\n{consensus_grounded_block}".strip()
    except Exception as c_err:
        print(f"Consensus engine notice: {c_err}", flush=True)







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



    try:



        from legal_ai.ranking.shadow_reranker import evaluate_candidate_relevance_shadow



        shadow_candidates, shadow_rerank_stats = evaluate_candidate_relevance_shadow(



            candidates=clean_candidates,



            query_plan=legal_query_plan,



            query_text=effective_user_query



        )



    except (ImportError, ModuleNotFoundError):



        shadow_candidates, shadow_rerank_stats = clean_candidates, {}







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



        sec6_heading = "   - ## 6. Pre-Arrest Bail Strategy (or Procedural Remedy)\n"



        sec6_directive = "Section 6 MUST focus on statutory pre-arrest bail under Section 498 Cr.P.C. or quashment under Section 561-A Cr.P.C."



    else:



        sec6_heading = "   - ## 6. Procedural Remedy & Appellate Strategy\n"



        sec6_directive = "Section 6 MUST be titled '## 6. Procedural Remedy & Appellate Strategy' and analyze civil/statutory interim remedies and appeals (Order XXXIX Rules 1 & 2 CPC, Order XLIII Rule 1(r) CPC appeal, s.115 CPC revision, or PRPA Rent Tribunal proceedings). NEVER discuss bail, FIR, or criminal procedure in civil/property/rent disputes."







    trap_instructions = build_pre_synthesis_trap_instructions(



        matter_type=matter_type,



        topics=detected_topics,



        abstain_topics=abstain_topics



    )







    synthesis_mode = os.environ.get("SYNTHESIS_MODE", "senior_counsel").lower()



    requests_strategy = query_requests_strategy(effective_user_query)







    current_system_date = datetime.now(timezone.utc).strftime("%d %B %Y")



    premise_directives = ""



    premise_corrections = getattr(legal_query_plan, "premise_corrections", []) if legal_query_plan else []



    if premise_corrections:



        pc_lines = ["MANDATORY PREMISE CORRECTION DIRECTIVE:"]



        for pc in premise_corrections:



            pc_lines.append(f"- {pc.get('mandatory_opening_thesis')}")



        pc_lines.append("You MUST open Section 1 with this explicit premise correction.\n")



        premise_directives = "\n".join(pc_lines)







    if synthesis_mode == "senior_counsel":



        user_synthesis_content = (



            f"FACTUAL MATRIX / LEGAL QUERY:\n{effective_user_query}\n\n"



            f"CURRENT SYSTEM DATE: {current_system_date}\n\n"



            f"STATUTORY & CURRENT LAW FRAMEWORK:\n{formatted_current_law_block}\n\n"



            f"{precedent_context_block}\n\n"



            f"{trap_instructions}\n\n"



            f"{premise_directives}\n\n"



            "Draft the exhaustive, authoritative 8-part Senior Counsel legal opinion addressing this query.\n\n"



            "MANDATORY PACING & STRUCTURE INSTRUCTIONS:\n"



            "1. TOTAL WORD BUDGET: The entire memorandum should be between 2,500 and 3,500 words across all 8 sections (approx 300-400 words per section). Keep analysis crisp, incisive, and authoritative so that you never exhaust the token window before concluding.\n"



            "2. ALL 8 SECTIONS ARE STRICTLY MANDATORY:\n"



            "   - ## 1. Executive Summary & Legal Opinion\n"



            "   - ## 2. Statutory & Procedural Framework\n"



            "   - ## 3. Controlling Judicial Precedents & Case Matrix\n"



            "   - ## 4. Substantive Legal Analysis & Doctrine\n"



            "   - ## 5. Application of Law to Facts\n"



            f"{sec6_heading}"



            "   - ## 7. Recommendations & Litigation Roadmap\n"



            "   - ## 8. Appendix: Research Scope & Unlocated Authorities\n"



            f"3. {sec6_directive}\n"



            "4. YOU MUST COMPLETE SECTION 8 BEFORE CONCLUDING.\n"



            "5. CLOSED-WORLD CITATION & PROPOSITION GROUNDING RESTRICTIONS:\n"



            "   - You may ONLY cite superior court precedents explicitly listed in the PRECEDENT table or cards above.\n"



            "   - STRICT RATIO GROUNDING: Every citing sentence MUST strictly reflect what the cited case actually decided as set forth in 'Holding / Ratio' and 'Key Paragraphs'. Do NOT extrapolate beyond the exact legal proposition decided.\n"



            "   - RESPECT NEGATIVE BOUNDARIES: Strictly adhere to 'Negative Boundary (What this case does NOT decide)'—never claim an authority decided matters outside its holding, never convert a leave grant into an automatic decree, and do NOT add statutory durations or penalties not affirmed in the ratio.\n"



            "   - NO BARE STRING-CITATIONS: Never cite a precedent as part of an ungrounded string-citation without substantive doctrinal engagement in the narrative.\n"



            "6. STRICT PROHIBITION ON ARTIFICIAL CERTIFICATIONS & FAKE METADATA:\n"



            "   - NEVER append 'Counsel's Certification', 'Prepared by Senior Counsel', '[Current Date]', 'Word Count: ...', or 'All 8 Sections Completed'.\n"



            "   - Output substantive legal analysis only; conclude Section 8 cleanly without appending any signatory or certification metadata.\n"



            "7. STRICT RULE ON SPECIFIC PROPOSITION QUERIES:\n"



            "   - When the user asks 'Cite the judgment holding [X]', if none of the retrieved precedents squarely decides X, you MUST state: 'I did not find a case that squarely holds this. The closest decisions are: [A, B] but note their limits: [why they do not reach X].'\n"



            "   - Banned unless grounded: 'definitively held', 'landmark authority', 'settled landmark precedent'.\n"



            "8. FIDELITY: Ensure all statutory references and holdings reflect the exact retrieved text without extrapolation.\n"



        )



    else:



        # Default: Judgment-First Mode



        has_statute_text = "STATUTORY VERBATIM TEXT" in formatted_current_law_block



        is_statute_missing, missing_statute_name = check_missing_statutory_source(



            query_text=effective_user_query,



            query_plan=legal_query_plan



        )



        if has_statute_text:



            is_statute_missing = False







        missing_statute_directive = ""



        if is_statute_missing:



            missing_statute_directive = (



                f"MANDATORY MISSING STATUTORY SOURCE DIRECTIVE:\n"



                f"The complete official bare-act text of {missing_statute_name} is unavailable in retrieved sources.\n"



                f"Base analysis on judicial references and verified provisions. Do not fabricate statutory quotes or insert warning banners.\n\n"



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



            + ("[Official verbatim bare-act statutory text is provided in the STATUTORY & CURRENT LAW FRAMEWORK above. You MUST quote and extract the provisions directly from that text. Do NOT state that statutory text is unavailable. Label the text as 'ingested, unreviewed' with source page and hash.]\n- [Act/Statute name] — [Section number]: [Verbatim quotation and explanation]\n\n" if has_statute_text else "> Statutory text unavailable in retrieved sources. The analysis is based only on judicial references.\n- [Act/Statute name] — [Section number]: [Short explanation]\n\n")



            + "## Judicial Authorities\n"



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



        "ACCURACY: Ensure all statements are strictly grounded in retrieved sources."



        )







    synthesis_max_tokens = int(os.environ.get("MAX_SYNTHESIS_TOKENS", "8192"))

    if job_id in jobs_store:

        jobs_store[job_id]["final_user_prompt"] = user_synthesis_content

        jobs_store[job_id]["final_system_prompt"] = system_prompt



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







    # Deterministic Relevant Provisions Assembly directly from Unified Statute Store



    if verified_statutory_provisions:



        prov_blocks = []



        for p in verified_statutory_provisions:



            cid = p.get("canonical_id", "")



            title = p.get("title", "")



            act_name = p.get("act_name") or p.get("display_name") or p.get("act_code") or "Statute"



            if "Section " in act_name and ", " in act_name:



                act_name = act_name.split(", ", 1)[-1]



            sec_num = p.get("primary_num") or p.get("section") or (cid.split("_SEC_")[-1] if "_SEC_" in cid else "")



            txt_val = p.get("text_cleaned") or p.get("text") or p.get("verbatim_text") or ""



            if isinstance(txt_val, dict):



                txt_val = txt_val.get("text") or str(txt_val)



            txt = str(txt_val)



            p_page = p.get("source_page") or "unspecified"



            p_hash = p.get("content_hash") or ""



            p_src = p.get("source_file") or "Official Gazette / Pakistan Code"



            p_tier = p.get("tier") or "ingested, unreviewed"



            p_tier = p_tier.replace("_", ", ") if "ingested_unreviewed" in p_tier else p_tier







            quoted_lines = [f"> {line}" if line.strip() else ">" for line in txt.strip().splitlines()]
            body_quoted = "\n".join(quoted_lines)

            # DigiLawyer Clean Presentation: Section Name, Plain-English role, and blockquote
            block = (
                f"### Section {sec_num} - {title}, {act_name.upper()}\n"
                f"Section {sec_num} sets out the controlling statutory provisions governing this matter.\n\n"
                f"{body_quoted}"
            )



            prov_blocks.append(block)







        deterministic_prov_section = "## Relevant Provisions\n" + "\n\n".join(prov_blocks) + "\n"



        # Replace whatever the model generated under ## Relevant Provisions with deterministic code output



        prov_pattern = re.compile(r'## Relevant Provisions[\s\S]*?(?=\n## Judicial Authorities|\n## Application to Query|\Z)', re.IGNORECASE)



        if prov_pattern.search(clean_answer):



            clean_answer = prov_pattern.sub(lambda m: deterministic_prov_section + "\n", clean_answer)



        else:



            # Prepend after Legal Issue if missing



            issue_match = re.search(r'(## Legal Issue[\s\S]*?\n\n)', clean_answer)



            if issue_match:



                clean_answer = clean_answer.replace(issue_match.group(1), issue_match.group(1) + deterministic_prov_section + "\n\n")







    # General Statute Claim Support Verification



    try:



        from core.statute_claim_verifier import verify_memo_statutory_claims



        stored_claims_map = {}
        primary_sec = ""
        for p in verified_statutory_provisions:
            cid = str(p.get("canonical_id") or p.get("act_code") or "PROVISION")
            txt_val = p.get("text_cleaned") or p.get("text") or ""
            if isinstance(txt_val, dict):
                txt_val = " ".join(str(v) for v in txt_val.values())
            stored_claims_map[cid] = str(txt_val)
            if not primary_sec:
                primary_sec = str(p.get("primary_num") or p.get("section") or "")
        claim_support_res = verify_memo_statutory_claims(clean_answer, stored_claims_map, primary_section=primary_sec)



        log_runtime_diagnostic("STATUTE_CLAIM_SUPPORT_RESULT", claim_support_res.to_dict())



    except Exception as cs_err:



        log_runtime_diagnostic("STATUTE_CLAIM_SUPPORT_ERR", str(cs_err))







    # Claim-to-source verification and scrubbing pass



    claim_verification = verify_and_scrub_memo_claims(



        clean_answer,



        retrieved_precedents=precedent_cards,



        statutory_context=formatted_current_law_block,



        query_text=effective_user_query



    )



    clean_answer = claim_verification.cleaned_text







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



    verification_report_payload["claim_verification"] = {



        "violations": claim_verification.violations,



        "verified_claims": claim_verification.verified_claims



    }



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

    # ORDER 1.7 & 1.10 & 1.11: MEMORANDUM VERIFIER GATE, REGENERATION & SYSTEM DISPUTED BANNER FLOW
    from legal_ai.verification.memo_verifier import (
        verify_memorandum_text,
        MemorandumVerificationBlockedError,
        assemble_and_verify_memorandum,
        attach_system_disputed_banner
    )

    # Initial verification attempt (Attempt 1)
    verification_gate = verify_memorandum_text(clean_answer, extra_authorities=precedent_cards)
    if not verification_gate.get('passed', False):
        disputed_notices = verification_gate.get('disputed_notices', [])
        failures = verification_gate.get('failures', [])
        if disputed_notices:
            re_gate = assemble_and_verify_memorandum(clean_answer, disputed_notices, extra_authorities=precedent_cards)
            if re_gate.get('passed', False):
                clean_answer = re_gate.get('assembled_text', attach_system_disputed_banner(clean_answer, disputed_notices))
                verification_gate = re_gate

    # ORDER 1.11 - ITEM 2: Automatic Regeneration Loop (Max 2 Attempts)
    attempts_history = [{
        "attempt": 1,
        "passed": bool(verification_gate.get("passed", False)),
        "total_failures": verification_gate.get("total_failures", 0),
        "failures_sample": [f.get("issue") or f.get("reason") for f in verification_gate.get("failures", [])[:5]]
    }]

    if not verification_gate.get('passed', False):
        print(f"[JOB {job_id}] Attempt 1 blocked with {verification_gate.get('total_failures', 0)} failures. Triggering Attempt 2 regeneration with feedback constraints...", file=sys.stderr, flush=True)
        # Formulate feedback constraints from Attempt 1 failures
        feedback_constraints = "\n\nCRITICAL REMEDIATION CONSTRAINTS (PRIOR DRAFT VIOLATIONS):\n"
        for f in verification_gate.get("failures", [])[:8]:
            feedback_constraints += f"- [{f.get('rule', '')} {f.get('category', '')}] {f.get('issue') or f.get('reason')}\n"
        feedback_constraints += "Enforce: Quote official statutory texts verbatim; cite verified section/subsections only; eliminate unsourced analytical commentary.\n"

        try:
            regen_content = user_synthesis_content + "\n\n" + feedback_constraints
            regen_message = await safe_create_anthropic_message(
                model=CLAUDE_MODEL,
                max_tokens=synthesis_max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": regen_content}]
            )
            regen_raw = ""
            for block in getattr(regen_message, "content", []):
                if getattr(block, "type", None) == "text":
                    regen_raw += block.text

            if regen_raw.strip():
                regen_clean = purge_debug_warnings(regen_raw)
                regen_gate = verify_memorandum_text(regen_clean, extra_authorities=precedent_cards)
                if not regen_gate.get('passed', False):
                    r_disputed = regen_gate.get('disputed_notices', [])
                    r_failures = regen_gate.get('failures', [])
                    if r_disputed:
                        re_re_gate = assemble_and_verify_memorandum(regen_clean, r_disputed, extra_authorities=precedent_cards)
                        if re_re_gate.get('passed', False):
                            regen_clean = re_re_gate.get('assembled_text', attach_system_disputed_banner(regen_clean, r_disputed))
                            regen_gate = re_re_gate

                attempts_history.append({
                    "attempt": 2,
                    "passed": bool(regen_gate.get("passed", False)),
                    "total_failures": regen_gate.get("total_failures", 0),
                    "failures_sample": [f.get("issue") or f.get("reason") for f in regen_gate.get("failures", [])[:5]]
                })

                if regen_gate.get('passed', False):
                    clean_answer = regen_clean
                    verification_gate = regen_gate
        except Exception as regen_ex:
            print(f"[JOB {job_id}] Regeneration attempt error: {regen_ex}", file=sys.stderr, flush=True)

    # DigiLawyer Parity: Surgical Quote Omission before blocking
    if not verification_gate.get('passed', False):
        from legal_ai.verification.memo_verifier import omit_unverified_blockquotes
        failures = verification_gate.get("failures", [])
        if any(f.get("category") in ("MISATTRIBUTED_QUOTE", "UNMATCHED_QUOTE") for f in failures):
            clean_answer = omit_unverified_blockquotes(clean_answer, failures)
            verification_gate = verify_memorandum_text(clean_answer, extra_authorities=precedent_cards)

    if not verification_gate.get('passed', False):
        print(
            f'[JOB {job_id}] MEMORANDUM VERIFICATION NOTICE: {len(verification_gate.get("failures", []))} violations detected after {len(attempts_history)} attempt(s).',
            file=sys.stderr,
            flush=True,
        )
        # Classify specific error category
        failures = verification_gate.get("failures", [])
        categories = {f.get("category") for f in failures}
        if "MISATTRIBUTED_QUOTE" in categories or "UNMATCHED_QUOTE" in categories:
            err_cat = "STATUTORY_MISQUOTATION"
        elif "UNVERIFIED_AUTHORITY" in categories:
            has_fake_page = any(
                str(f.get("span", "")).strip().split()[-1].isdigit() and int(str(f.get("span", "")).strip().split()[-1]) > 2500
                for f in failures if f.get("category") == "UNVERIFIED_AUTHORITY" and str(f.get("span", "")).strip().split()
            )
            err_cat = "FABRICATED_CITATION" if has_fake_page else "UNVERIFIED_AUTHORITY"
        elif "UNSOURCED_ANALYSIS" in categories:
            err_cat = "UNSOURCED_ANALYSIS"
        elif "CITED_PROVISION_NOT_IN_VERIFIED_STORE" in categories:
            err_cat = "UNSOURCED_PROVISION_CITATION"
        elif "DISPUTED_TEXT_UNNOTICED" in categories:
            err_cat = "DISPUTED_TEXT_UNNOTICED"
        else:
            err_cat = "VERIFICATION_GATE_REJECTION"

        # Collect unverified authorities/citations if any
        unverified_auths = []
        for f in failures:
            if f.get("category") == "UNVERIFIED_AUTHORITY" or f.get("rule") == "(c)":
                span = f.get("span")
                if span and span not in unverified_auths:
                    unverified_auths.append(span)

        # ORDER 2.1 - ITEM 2: Never extract case names or authorities from the user query.
        # Authorities are verified exclusively from the generated memorandum draft.

        if err_cat == "FABRICATED_CITATION":
            citations_str = ", ".join(f"`{a}`" for a in unverified_auths) if unverified_auths else "the cited judicial authority"
            safe_reason = (
                f"The authority {citations_str} could not be verified in authoritative Pakistani law reports "
                f"(SCMR, PLD, CLD, CLC, PCrLJ, MLD, PTD, PLC) or the verified precedent index. Output withheld to prevent hallucination."
            )
            retry_guidance = (
                f"Please verify the citation journal, publication year, and page number for {citations_str}. "
                f"In Pakistan, annual volume pagination for law journals rarely exceeds 2,000–2,500 pages."
            )
        elif err_cat == "STATUTORY_MISQUOTATION":
            safe_reason = "The generated draft contained statutory quotations that differed from authentic gazette texts."
            retry_guidance = "Ensure all statutory quotes verbatim match authentic gazettes and cite only in-force provisions from verified acts."
        elif err_cat == "UNSOURCED_ANALYSIS":
            safe_reason = "The generated draft contained analysis claims not directly anchored in verified statutory gazettes or indexed judicial holdings."
            retry_guidance = "Anchor legal assertions directly to verified gazettes or indexed precedents."
        else:
            safe_reason = (
                "The generated memorandum could not be verified against official statutory gazettes and "
                "the verified judicial precedent index. Output withheld to protect legal accuracy."
            )
            retry_guidance = (
                "Ensure all statutory quotes verbatim match authentic gazettes, cite only in-force provisions from "
                "verified acts, and omit uncited speculative factual assertions."
            )

        # Build verified_statute_fallback with tier labels and disputed banner
        verified_fallback = []
        for p in verified_statutory_provisions:
            cid = p.get("canonical_id") or p.get("act_code") or "PROVISION"
            tier = p.get("tier", "tier_1")
            disp_name = p.get("display_name") or p.get("act_name") or cid
            txt = p.get("text_cleaned") or p.get("text") or ""
            if isinstance(txt, dict):
                txt = " ".join(str(v) for v in txt.values())

            # Check if disputed
            is_disputed = (p.get("verification_status") == "disputed_boundary_repaired" or 
                           p.get("status") == "disputed" or 
                           "FIO_2001_SEC_22" in str(cid))
            banner_prefix = ""
            if is_disputed:
                banner_prefix = "> ⚠️ **Disputed Gazette Note**: Official prints of this provision contain contested text variations. Independent human verification against authenticated gazette prints is recommended prior to formal court reliance.\n\n"

            # ORDER 2.1 - ITEM 5: Check if provision has stored text
            has_text = bool(txt and str(txt).strip() and tier != "heading_only")
            if not has_text:
                rendered_text = "no text available"
            else:
                rendered_text = banner_prefix + f"#### {disp_name}\n\n" + re.sub(r'\b(Provided that)\b', r'\n\n> *\1*', re.sub(r'(?<!sub-section\s)(?<!sub -section\s)(?<!section\s)(?<!order\s)(?<=\s)(\([0-9]+\))\s*', r'\n\n**\1** ', txt))

            verified_fallback.append({
                "canonical_id": cid,
                "display_name": disp_name,
                "tier": "heading_only" if not has_text else tier,
                "is_disputed": is_disputed,
                "has_text": has_text,
                "text": rendered_text
            })

        blocked_payload = {
            'status': 'error',
            'stage': 'verification_blocked',
            'error': 'MEMORANDUM_VERIFICATION_FAILED',
            'error_category': err_cat,
            'safe_reason': safe_reason,
            'retry_guidance': retry_guidance,
            'unverified_citations': unverified_auths,
            'query_text': effective_user_query,
            'verified_statute_fallback': verified_fallback,
            'verified_precedents_fallback': precedent_cards,
            'precedent_cards': precedent_cards,
            'attempts': attempts_history,
            'early_display': None,
            'result': None,
            'verification_report': verification_gate,
            'completed_at': datetime.now(timezone.utc),
        }
        if job_id in jobs_store:
            jobs_store[job_id].update(blocked_payload)
        raise MemorandumVerificationBlockedError(verification_gate, blocked_payload=blocked_payload)

    # 8. Database Persistence (Supabase queries table)



    
    # STAGE 5 GATE 2: ANTI-PATTERN GUARDRAIL & GUARDIAN INTERVENTION
    from legal_ai.verification.anti_pattern_guard import AntiPatternGuard
    anti_guard = AntiPatternGuard()
    guard_res = anti_guard.check_text(clean_answer)
    if not guard_res["is_clean"]:
        clean_answer = guard_res["sanitized_text"]
        guardian_notice = anti_guard.format_guardian_notice(guard_res["guardian_interventions"])
        if guardian_notice:
            clean_answer = clean_answer + "\n\n---\n\n" + guardian_notice

    from legal_ai.synthesis.memorandum_generator import sanitize_partner_markdown_presentation
    clean_answer = sanitize_partner_markdown_presentation(clean_answer)

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



