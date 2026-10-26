import re

with open("main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

targets = [
    r'/query/\{job_id\}',
    r'/continue',
    r'/generate-pleading',
    r'/export/court-pleading',
    r'def log_runtime_diagnostic',
    r'def run_research_pipeline',
    r'queries.*insert',
    r'from_\("queries"\)',
    r'table\("queries"\)',
    r'from_\("diary"\)',
    r'table\("diary"\)',
    r'event:\s*done',
]

for i, line in enumerate(lines, 1):
    for t in targets:
        if re.search(t, line, re.I):
            print(f"{i}: {line.strip()[:110]}")
