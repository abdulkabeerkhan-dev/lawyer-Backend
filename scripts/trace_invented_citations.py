import subprocess
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

print("=== CHECKING reindex_queue.json ===")
queue_file = "reindex_queue.json"
if os.path.exists(queue_file):
    with open(queue_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    print(f"File exists: {queue_file} ({len(lines)} lines)")
    for i, line in enumerate(lines[:30]):
        print(f"  Line {i+1}: {line.strip()[:100]}")
else:
    print(f"File {queue_file} does not exist.")

print("\n=== TRACING 'Muhammad Nazir v. Sakhi Muhammad' VIA GIT LOG -S ===")
try:
    cmd = ["git", "log", "-S", "Muhammad Nazir", "--oneline"]
    res = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace")
    print("Commits mentioning 'Muhammad Nazir':\n", res)
    
    cmd2 = ["git", "log", "-S", "Sakhi Muhammad", "--oneline"]
    res2 = subprocess.check_output(cmd2, text=True, encoding="utf-8", errors="replace")
    print("Commits mentioning 'Sakhi Muhammad':\n", res2)

    # Let's inspect the earliest commit
    commits = [l.split()[0] for l in res.strip().split("\n") if l.strip()]
    if commits:
        earliest = commits[-1]
        print(f"\nDiff of earliest commit {earliest}:")
        diff = subprocess.check_output(["git", "show", "--stat", earliest], text=True, encoding="utf-8", errors="replace")
        print(diff)
except Exception as e:
    print("Error tracing via git log:", e)
