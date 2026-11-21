import json
import os
from pathlib import Path

targets = [
    ("PPC_1860", "34", "PPC 34"),
    ("PPC_1860", "302", "PPC 302"),
    ("PPC_1860", "420", "PPC 420"),
    ("PPC_1860", "489F", "PPC 489-F"),
    ("CRPC_1898", "154", "CrPC 154"),
    ("CRPC_1898", "497", "CrPC 497"),
    ("CRPC_1898", "561A", "CrPC 561-A"),
    ("CPC_1908", "11", "CPC 11"),
    ("CPC_1908", "115", "CPC 115"),
    ("CPC_1908", "ORD_VII_R_11", "CPC Order VII Rule 11"),
    ("CONST_1973", "10A", "Const Art 10A"),
    ("CONST_1973", "199", "Const Art 199"),
    ("FIO_2001", "9", "FIO 9"),
    ("FIO_2001", "15", "FIO 15"),
    ("FIO_2001", "22", "FIO 22"),
    ("NAO_1999", "9", "NAO 9"),
    ("NAO_1999", "10", "NAO 10"),
    ("NAO_1999", "24", "NAO 24"),
    ("ITO_2001", "111", "ITO 111"),
    ("ITO_2001", "122", "ITO 122"),
    ("SALES_TAX_1990", "11", "Sales Tax Act 11"),
    ("CONTRACT_1872", "73", "Contract Act 73"),
    ("SRA_1877", "42", "Specific Relief Act 42"),
    ("QSO_1984", "17", "Qanun-e-Shahadat Art 17")
]

staging_dir = Path("data/statutes_v3_staging")

print("=" * 80)
print("VERIFYING 24 CORE STATUTORY PROVISIONS IN STAGING")
print("=" * 80)

found_count = 0
for act_code, sec_key, label in targets:
    fpath = staging_dir / f"{act_code}.json"
    records = []
    if fpath.exists():
        with open(fpath, "r", encoding="utf-8") as fp:
            records = json.load(fp)
    else:
        matching = list(staging_dir.glob(f"*{act_code}*.json"))
        if matching:
            fpath = matching[0]
            with open(fpath, "r", encoding="utf-8") as fp:
                records = json.load(fp)
                
    # Also check legacy if not found or if CPC order
    if not records or "ORD" in sec_key:
        leg_path = staging_dir / "statutes_v2_legacy.json"
        if leg_path.exists():
            with open(leg_path, "r", encoding="utf-8") as fp:
                legacy_recs = json.load(fp)
            records.extend(legacy_recs)
        
    # Search for matching section
    matched_rec = None
    for r in records:
        s = r.get("section", "").replace("-", "").replace(" ", "").replace("_", "").upper()
        cid = r.get("canonical_id", "")
        clean_key = sec_key.replace("-", "").replace(" ", "").replace("_", "").upper()
        
        if s == clean_key or cid.endswith(f"_{sec_key}") or cid.endswith(f"_{clean_key}") or clean_key in s:
            matched_rec = r
            break
            
    if matched_rec:
        found_count += 1
        txt = matched_rec.get("text", "")
        cid = matched_rec.get("canonical_id")
        hdg = matched_rec.get("heading")
        print(f"\n[OK] {label} -> canonical_id: {cid}")
        print(f"     Heading: {hdg}")
        print(f"     First 200 chars: {repr(txt[:200])}")
    else:
        print(f"\n[MISSING] {label} (act: {act_code}, key: {sec_key}) not found in {fpath.name}")
        # print some sample sections
        sample_secs = [r.get("section") for r in records[:10]]
        print(f"     Sample sections: {sample_secs}")

print(f"\nTotal verified: {found_count}/{len(targets)}")
