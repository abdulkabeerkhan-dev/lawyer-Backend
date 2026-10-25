import subprocess

cmd = ["git", "grep", "Sakhi Muhammad", "980f611"]
res = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace")
print("git grep 'Sakhi Muhammad' 980f611:")
print(res)

# Also check lines around 2013_SCMR_51 in reindex_queue.json
with open("reindex_queue.json", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "2013_SCMR_51" in l or "2013 SCMR 51" in l:
        print(f"reindex_queue.json line {i+1}: {l.strip()}")
        # print surrounding
        for j in range(max(0, i-2), min(len(lines), i+3)):
            print(f"  [{j+1}] {lines[j].strip()}")
