import subprocess
import json

for commit in ["2ed0c3a", "1df39f2", "c17904c"]:
    try:
        out = subprocess.check_output(["git", "show", f"{commit}:data/unified_statutes/PPC_1860.json"], text=True, encoding="utf-8")
        data = json.loads(out)
        recs = [x for x in data if x.get("canonical_id") in ["PPC_1860_SEC_409", "PPC_1860_SEC_420", "PPC_1860_SEC_489F"]]
        print(f"=== Commit {commit} ===")
        for r in recs:
            print(r.get("canonical_id"), "tier:", r.get("tier"), "status:", r.get("status"), "source_page:", r.get("source_page"))
    except Exception as e:
        print(f"Error checking {commit}: {e}")
