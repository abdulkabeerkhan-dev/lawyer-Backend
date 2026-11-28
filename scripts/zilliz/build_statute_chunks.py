r"""
scripts/zilliz/build_statute_chunks.py

Long statute provisions get one embedding in `statutes_v3`, so their key point is diluted and
short provisions outrank them. This script splits every in-force provision longer than
MIN_CHARS into ~TARGET-character pieces (on sub-section / clause / sentence boundaries), each
prefixed with "{act_name}\nSection {section}: {heading}", and stores them in a separate
collection `statutes_v3_chunks` (dense voyage-4-large + in-engine BM25). Search maps a chunk hit
back to its parent provision (`parent_id`). `statutes_v3` itself is not changed.

Usage:
  python scripts/zilliz/build_statute_chunks.py --create          # create the collection
  python scripts/zilliz/build_statute_chunks.py --all             # (re)build every long provision
  python scripts/zilliz/build_statute_chunks.py --ids ids.json    # rebuild these provisions only
Env: ZILLIZ_URI, ZILLIZ_TOKEN, VOYAGE_API_KEY
"""
import argparse, glob, json, os, re, sys, time, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COLL = os.environ.get("ZILLIZ_STATUTE_CHUNKS_COLLECTION", "statutes_v3_chunks")
MIN_CHARS, TARGET = 1500, 1200
Z = os.environ.get("ZILLIZ_URI", "").rstrip("/")


def post(url, body, token):
    for a in range(6):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=180))
        except Exception:
            if a == 5:
                raise
            time.sleep(3 * (a + 1))


def zpost(path, body):
    res = post(Z + path, body, os.environ["ZILLIZ_TOKEN"])
    if res.get("code") not in (0, None):
        raise RuntimeError(f"{path}: {res}")
    return res


def embed(texts):
    res = post("https://api.voyageai.com/v1/embeddings",
               {"input": texts, "model": "voyage-4-large", "input_type": "document"}, os.environ["VOYAGE_API_KEY"])
    return [d["embedding"] for d in res["data"]]


_BREAK = re.compile(r"(?=\s(?:\(\d+[A-Z]?\)|\([a-z]{1,4}\)|Explanation\b|Illustrations?\b|Provided\b)\s)")


def split_text(text):
    """Pack sub-section / clause pieces into chunks of about TARGET characters; a piece that is
    itself too long is cut at sentence ends. The last sentence of a chunk opens the next one."""
    pieces = []
    for part in _BREAK.split(text):
        part = part.strip()
        if not part:
            continue
        while len(part) > TARGET * 1.5:
            cut = part.rfind(". ", 0, TARGET)
            cut = cut + 1 if cut > TARGET // 3 else TARGET
            pieces.append(part[:cut].strip())
            part = part[cut:].strip()
        pieces.append(part)
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 1 > TARGET:
            chunks.append(cur)
            tail = re.split(r"(?<=[.;:])\s", cur)[-1]
            cur = (tail + " " + p) if len(tail) < 300 else p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        chunks.append(cur)
    return chunks


def load_provisions():
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data/statutes_v3_staging/*.json"))):
        for r in json.load(open(f, encoding="utf-8")):
            out.setdefault(r["canonical_id"], r)
    return out


def rows_for(r):
    text = (r.get("text") or "").strip()
    if len(text) <= MIN_CHARS or not r.get("in_force", True) or r.get("omitted") or r.get("historical"):
        return []
    head = f"{r.get('act_name', '')}\nSection {r.get('section', '')}: {r.get('heading', '')}".strip()
    rows = []
    for i, ch in enumerate(split_text(text)):
        rows.append({
            "chunk_id": f"{r['canonical_id']}#{i}"[:160], "parent_id": r["canonical_id"][:128],
            "chunk_index": i, "act_code": str(r.get("act_code", ""))[:64], "act_name": str(r.get("act_name", ""))[:256],
            "section": str(r.get("section", ""))[:64], "heading": str(r.get("heading", ""))[:511],
            "domain": str(r.get("domain") or "")[:64], "provision_type": str(r.get("provision_type") or "")[:32],
            "in_force": True, "historical": False, "omitted": False,
            "text": (head + "\n\n" + ch).encode()[:65000].decode("utf-8", "ignore"),
        })
    return rows


def create():
    schema = {"autoId": False, "enableDynamicField": False, "fields": [
        {"fieldName": "chunk_id", "dataType": "VarChar", "isPrimary": True, "elementTypeParams": {"max_length": 160}},
        {"fieldName": "parent_id", "dataType": "VarChar", "elementTypeParams": {"max_length": 128}},
        {"fieldName": "chunk_index", "dataType": "Int64"},
        {"fieldName": "act_code", "dataType": "VarChar", "elementTypeParams": {"max_length": 64}},
        {"fieldName": "act_name", "dataType": "VarChar", "elementTypeParams": {"max_length": 256}},
        {"fieldName": "section", "dataType": "VarChar", "elementTypeParams": {"max_length": 64}},
        {"fieldName": "heading", "dataType": "VarChar", "elementTypeParams": {"max_length": 512}},
        {"fieldName": "domain", "dataType": "VarChar", "elementTypeParams": {"max_length": 64}},
        {"fieldName": "provision_type", "dataType": "VarChar", "elementTypeParams": {"max_length": 32}},
        {"fieldName": "in_force", "dataType": "Bool"}, {"fieldName": "historical", "dataType": "Bool"},
        {"fieldName": "omitted", "dataType": "Bool"},
        {"fieldName": "text", "dataType": "VarChar", "elementTypeParams": {"max_length": 65535, "enable_analyzer": True}},
        {"fieldName": "dense", "dataType": "FloatVector", "elementTypeParams": {"dim": 1024}},
        {"fieldName": "sparse", "dataType": "SparseFloatVector"}],
        "functions": [{"name": "chunks_text_bm25", "type": "BM25", "inputFieldNames": ["text"], "outputFieldNames": ["sparse"]}]}
    idx = [{"fieldName": "dense", "metricType": "COSINE", "indexName": "dense", "indexType": "AUTOINDEX"},
           {"fieldName": "sparse", "metricType": "BM25", "indexName": "sparse", "indexType": "AUTOINDEX"},
           {"fieldName": "parent_id", "indexName": "parent_id", "indexType": "AUTOINDEX"}]
    zpost("/v2/vectordb/collections/create", {"collectionName": COLL, "schema": schema, "indexParams": idx})
    print("created", COLL)


def build(ids):
    provs = load_provisions()
    targets = [provs[i] for i in ids if i in provs]
    if ids is not None and len(targets) != len(ids):
        print("unknown ids skipped:", len(ids) - len(targets))
    # drop the old chunks of these provisions first, so a shorter rewrite leaves no stale pieces
    for k in range(0, len(targets), 200):
        part = [r["canonical_id"] for r in targets[k:k + 200]]
        zpost("/v2/vectordb/entities/delete", {"collectionName": COLL, "filter": "parent_id in " + json.dumps(part)})
    rows = [row for r in targets for row in rows_for(r)]
    print(f"{len(targets)} provisions -> {len(rows)} chunks")
    for k in range(0, len(rows), 64):
        batch = rows[k:k + 64]
        for row, vec in zip(batch, embed([b["text"] for b in batch])):
            row["dense"] = vec
        zpost("/v2/vectordb/entities/upsert", {"collectionName": COLL, "data": batch})
        if k % 1280 == 0:
            print(f"  {k + len(batch)}/{len(rows)}", flush=True)
    print("done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ids")
    a = ap.parse_args()
    if a.create:
        create()
    if a.all:
        build(list(load_provisions()))
    elif a.ids:
        build(json.load(open(a.ids)))
