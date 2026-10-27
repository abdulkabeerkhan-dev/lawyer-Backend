import os
import re

qp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'legal_ai', 'query_engine', 'query_processor.py')
with open(qp_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Regex find statute_framework_res block
match1 = re.search(r'(statute_framework_res = inject_statutory_framework[^\n]*\n(?:[ \t]*\n)*[ \t]*if statute_framework_res\.get\("statute_block"\):[^\n]*\n(?:[ \t]*\n)*[ \t]*formatted_current_law_block = [^\n]*\n)', content)
assert match1, "Match 1 not found!"

consensus_code = """
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
            formatted_current_law_block = f"{formatted_current_law_block}\\n\\n{consensus_grounded_block}".strip()
    except Exception as c_err:
        print(f"Consensus engine notice: {c_err}", flush=True)
"""

content = content[:match1.end()] + consensus_code + content[match1.end():]

# 2. Regex find inserted_row_id = job_id
match2 = re.search(r'(inserted_row_id = job_id\n)', content)
assert match2, "Match 2 not found!"

guard_code = """
    # STAGE 5 GATE 2: ANTI-PATTERN GUARDRAIL & GUARDIAN INTERVENTION
    from legal_ai.verification.anti_pattern_guard import AntiPatternGuard
    anti_guard = AntiPatternGuard()
    guard_res = anti_guard.check_text(clean_answer)
    if not guard_res["is_clean"]:
        clean_answer = guard_res["sanitized_text"]
        guardian_notice = anti_guard.format_guardian_notice(guard_res["guardian_interventions"])
        if guardian_notice:
            clean_answer = guardian_notice + "\\n\\n" + clean_answer

"""

content = content[:match2.start()] + guard_code + content[match2.start():]

with open(qp_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully applied Dual Track & Consensus pipeline into query_processor.py")
