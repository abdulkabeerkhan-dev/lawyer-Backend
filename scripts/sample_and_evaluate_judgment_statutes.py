import os
import random
import re
import json
from dotenv import load_dotenv
from pymilvus import MilvusClient

load_dotenv()

zclient = MilvusClient(uri=os.environ['ZILLIZ_URI'], token=os.environ['ZILLIZ_TOKEN'])

print("Sampling 300 random judgment chunks from judgments_v1...")

sample_size = 300
rows = zclient.query(
    collection_name="judgments_v1",
    filter="array_length(statutes) > 0",
    limit=sample_size,
    output_fields=["chunk_id", "case_key", "citation", "statutes", "text"]
)

print(f"Retrieved {len(rows)} judgment chunks.")

# Citation regex patterns to extract from text
ACT_PATTERNS = [
    (r'(?:Pakistan\s+Penal\s+Code|P\.?P\.?C\.?)\b.*?(?:section|s\.)\s*([0-9]{1,3}[A-Z]?(?:\s*\([0-9a-z]+\))?)', 'PPC_1860'),
    (r'(?:section|s\.)\s*([0-9]{1,3}[A-Z]?(?:\s*\([0-9a-z]+\))?)\s*(?:of\s+(?:the\s+)?)?(?:Pakistan\s+Penal\s+Code|P\.?P\.?C\.?)\b', 'PPC_1860'),
    (r'(?:Code\s+of\s+Criminal\s+Procedure|Cr\.?P\.?C\.?)\b.*?(?:section|s\.)\s*([0-9]{1,3}[A-Z]?(?:\s*\([0-9a-z]+\))?)', 'CRPC_1898'),
    (r'(?:section|s\.)\s*([0-9]{1,3}[A-Z]?(?:\s*\([0-9a-z]+\))?)\s*(?:of\s+(?:the\s+)?)?(?:Code\s+of\s+Criminal\s+Procedure|Cr\.?P\.?C\.?)\b', 'CRPC_1898'),
    (r'(?:Code\s+of\s+Civil\s+Procedure|C\.?P\.?C\.?)\b.*?(?:section|s\.)\s*([0-9]{1,3}[A-Z]?(?:\s*\([0-9a-z]+\))?)', 'CPC_1908'),
    (r'(?:section|s\.)\s*([0-9]{1,3}[A-Z]?(?:\s*\([0-9a-z]+\))?)\s*(?:of\s+(?:the\s+)?)?(?:Code\s+of\s+Civil\s+Procedure|C\.?P\.?C\.?)\b', 'CPC_1908'),
    (r'(?:Order\s+([IVXLCDM]+|[0-9]+)\s*,?\s*Rule\s+([0-9]{1,2}))\b.*?(?:C\.?P\.?C\.?|Code\s+of\s+Civil\s+Procedure)', 'CPC_1908_ORDER'),
    (r'(?:Constitution\s+(?:of\s+Pakistan)?)\b.*?(?:Article|Art\.)\s*([0-9]{1,3}[A-Z]?)', 'CONST_1973'),
    (r'(?:Article|Art\.)\s*([0-9]{1,3}[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:Constitution)\b', 'CONST_1973'),
    (r'(?:Financial\s+Institutions\s*\([^\)]*?\)\s*Ordinance|F\.?I\.?O\.?)\b.*?(?:section|s\.)\s*([0-9]{1,2}[A-Z]?(?:\s*\([0-9a-z]+\))?)', 'FIO_2001'),
    (r'(?:National\s+Accountability\s*Ordinance|N\.?A\.?O\.?)\b.*?(?:section|s\.)\s*([0-9]{1,2}[A-Z]?(?:\s*\([0-9a-z]+\))?)', 'NAO_1999'),
    (r'(?:Income\s+Tax\s*Ordinance|I\.?T\.?O\.?)\b.*?(?:section|s\.)\s*([0-9]{1,3}[A-Z]?)', 'ITO_2001'),
    (r'(?:Anti[- ]Terrorism\s*Act|A\.?T\.?A\.?)\b.*?(?:section|s\.)\s*([0-9]{1,2}[A-Z]?)', 'ATA_1997'),
    (r'(?:Qanun[- ]e[- ]Shahadat|Q\.?S\.?O\.?)\b.*?(?:Article|Art\.)\s*([0-9]{1,3}[A-Z]?)', 'QSO_1984'),
]

# Load alias map
with open('reports/citation_reconciliation_report.json', 'r', encoding='utf-8') as fp:
    alias_data = json.load(fp)
alias_map = alias_data.get('proposed_aliases', {})

def extract_mentions(text):
    mentions = set()
    for pat, act in ACT_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if act == 'CPC_1908_ORDER':
                ord_num = m.group(1).upper()
                rule_num = m.group(2)
                mentions.add(f"CPC_1908_ORD_{ord_num}_R_{rule_num}")
            elif act == 'CONST_1973':
                art_num = m.group(1).upper()
                mentions.add(f"CONST_1973_ART_{art_num}")
            else:
                sec_raw = m.group(1).upper().replace(' ', '')
                m_sub = re.match(r'^(\d+[A-Z]?)(?:\(([0-9a-z]+)\))?', sec_raw, re.I)
                if m_sub:
                    primary = m_sub.group(1)
                    sub = m_sub.group(2)
                    if sub:
                        mentions.add(f"{act}_SEC_{primary}_{sub.lower()}")
                    mentions.add(f"{act}_SEC_{primary}")
                else:
                    mentions.add(f"{act}_SEC_{sec_raw}")
    return mentions

def normalize_tag(tag):
    t = str(tag).upper().strip()
    return alias_map.get(t, t)

total_tp = 0
total_fp = 0
total_fn = 0

sample_comparisons = []

for row in rows:
    stored_tags = row.get("statutes", [])
    if isinstance(stored_tags, str):
        try:
            stored_tags = json.loads(stored_tags)
        except Exception:
            stored_tags = [s.strip() for s in stored_tags.split(",") if s.strip()]
    elif not isinstance(stored_tags, list):
        stored_tags = []

    stored_norm = set(normalize_tag(t) for t in stored_tags if t)
    
    txt = row.get("text", "")
    extracted_raw = extract_mentions(txt)
    extracted_norm = set(normalize_tag(t) for t in extracted_raw)

    tp = len(stored_norm & extracted_norm)
    fp = len(stored_norm - extracted_norm)
    fn = len(extracted_norm - stored_norm)

    total_tp += tp
    total_fp += fp
    total_fn += fn

    if len(sample_comparisons) < 10 and (fp > 0 or fn > 0):
        sample_comparisons.append({
            "chunk_id": row.get("chunk_id"),
            "case_key": row.get("case_key"),
            "citation": row.get("citation"),
            "stored": list(stored_norm),
            "extracted": list(extracted_norm),
            "tp": list(stored_norm & extracted_norm),
            "fp": list(stored_norm - extracted_norm),
            "fn": list(extracted_norm - stored_norm)
        })

precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

print("\n" + "=" * 80)
print("EVALUATION OF STORED JUDGMENT STATUTE TAGS AGAINST TEXT (300 CHUNKS)")
print("=" * 80)
print(f"Total Stored Tag Occurrences       : {total_tp + total_fp}")
print(f"Total Extracted In-Text Mentions   : {total_tp + total_fn}")
print(f"True Positives (Agreed mentions)   : {total_tp}")
print(f"False Positives (Stored in metadata but absent from chunk text): {total_fp}")
print(f"False Negatives (Mentioned in chunk text but missing from tags): {total_fn}")
print(f"PRECISION (Stored accuracy against chunk) : {precision * 100:.2f}%")
print(f"RECALL (Coverage of in-chunk mentions)    : {recall * 100:.2f}%")
print(f"F1 SCORE                                  : {f1 * 100:.2f}%")

print("\n--- SAMPLE DISCREPANCY COMPARISONS ---")
for i, comp in enumerate(sample_comparisons[:5], start=1):
    print(f"\n[{i}] Chunk: {comp['chunk_id']} | Case: {comp['case_key']} | Citation: {comp['citation']}")
    print(f"    Stored tags   : {comp['stored']}")
    print(f"    Extracted     : {comp['extracted']}")
    print(f"    FP (in stored, not in chunk): {comp['fp']}")
    print(f"    FN (in chunk, missed by tag): {comp['fn']}")
