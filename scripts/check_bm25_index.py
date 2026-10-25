import pickle
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with open("bm25_index.pkl", "rb") as f:
    data = pickle.load(f)

doc_metadata = data.get("doc_metadata", [])
doc_ids = data.get("doc_ids", [])
print(f"Total doc_ids: {len(doc_ids)}, doc_metadata: {len(doc_metadata)}")

for i, m in enumerate(doc_metadata):
    s = str(m)
    if "Sakhi Muhammad" in s:
        print(f"Index {i} | ID: {doc_ids[i] if i < len(doc_ids) else 'N/A'}")
        print(f"  Case title: {m.get('case_title')}")
        print(f"  Citation: {m.get('citation')}")
        print(f"  Snippet: {m.get('text', '')[:200]!r}\n")
