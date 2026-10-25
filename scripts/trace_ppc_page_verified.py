import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Run git log on PPC_1860.json looking for page_verified
cmd = ["git", "log", "-S", "page_verified", "--oneline", "--", "data/unified_statutes/PPC_1860.json"]
out = subprocess.check_output(cmd, text=True)
print("=== GIT LOG -S 'page_verified' for PPC_1860.json ===")
print(out)

# Also check git diff on the commit that introduced it
commits = [line.split()[0] for line in out.strip().split("\n") if line.strip()]
for c in commits:
    print(f"\n--- Commit {c} diff on PPC_1860.json ---")
    diff_out = subprocess.check_output(["git", "show", "--stat", c], text=True)
    print(diff_out)
