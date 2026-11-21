import sys
sys.path.insert(0, 'D:/lawyer-Backend')

# Let's run create_deterministic_fallback_plan with trace
import sys
from core.legal_query_planner import create_deterministic_fallback_plan

def trace_calls(frame, event, arg):
    if event == "line":
        code = frame.f_code
        if code.co_name == "create_deterministic_fallback_plan":
            lineno = frame.f_lineno
            dom = frame.f_locals.get("primary_domain")
            provs = frame.f_locals.get("provisions")
            if dom == "criminal" or (provs and len(provs) > 0):
                print(f"Line {lineno}: primary_domain={dom}, provisions={provs}")
    return trace_calls

sys.settrace(trace_calls)
plan = create_deterministic_fallback_plan("eviction notice")
sys.settrace(None)
print("Final plan domain:", plan.primary_domain)
