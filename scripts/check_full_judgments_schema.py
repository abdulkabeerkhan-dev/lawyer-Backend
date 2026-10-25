import re
import os

print("=== CHECKING full_judgments USAGE ACROSS CODEBASE ===")
cols_found = set()
for root, dirs, files in os.walk("."):
    if ".git" in root or "venv" in root: continue
    for file in files:
        if file.endswith(".py"):
            fpath = os.path.join(root, file)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "full_judgments" in content:
                # Find select(...) calls
                selects = re.findall(r'table\(["\']full_judgments["\']\)\.select\(["\']([^"\']+)["\']\)', content)
                froms = re.findall(r'from\(["\']full_judgments["\']\)\.select\(["\']([^"\']+)["\']\)', content)
                for s in selects + froms:
                    for col in s.split(","):
                        cols_found.add(col.strip())
                # Also find raw SQL
                sql_matches = re.findall(r'SELECT\s+([a-zA-Z0-9_,\s\*\.]+)\s+FROM\s+(?:public\.)?full_judgments', content, re.IGNORECASE)
                for sm in sql_matches:
                    for col in sm.split(","):
                        cols_found.add(col.strip())

print(f"Columns referenced in codebase: {sorted(list(cols_found))}")
