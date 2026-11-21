import json
import os
import re

acts = {
    'PPC_1860': ('Pakistan Penal Code (PPC),1860 (Under Review).txt', 511),
    'CPC_1908': ('Code of Civil Procedure (CPC) , 1908 (Under Review).txt', 158),
    'CONST_1973': ('Constitution of the Islamic Republic of Pakistan.txt', 280),
    'ITO_2001': ('Income Tax Ordinance, 2001 (Same as on the official website of FBR dated 31-06-2026).txt', 241),
    'SALES_TAX_1990': ('Sales Tax Act, 1990 (Same as on the official website of FBR dated 30-06-2026).txt', 76),
    'CRPC_1898': ('Code of Criminal Procedure (CrPC), 1898 (Under Review).txt', 565),
}

results = {}

for act_code, (fname, max_sec) in acts.items():
    staged_path = os.path.join('data', 'statutes_v3_staging', f'{act_code}.json')
    with open(staged_path, 'r', encoding='utf-8') as f:
        staged = json.load(f)
    
    staged_secs = set(r.get('section') for r in staged if r.get('section'))
    
    txt_path = os.path.join(r'D:\pakistan_code_text', fname)
    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        full_text = f.read()

    missing_nums = []
    for n in range(1, max_sec + 1):
        if str(n) not in staged_secs:
            missing_nums.append(n)
            
    print(f"\n=======================================================")
    print(f"ACT: {act_code} (Total missing integer sections: {len(missing_nums)})")
    print(f"=======================================================")
    
    act_evidence = []
    no_evidence = []
    
    for n in missing_nums:
        # Search patterns in full_text
        # e.g. "93. [Omitted...", "Section 93. [Rep...", "93. Rep. by", "[93. Omitted", "54. [Omitted", "110. [Omitted"
        pats = [
            rf'(?:^|\n)\s*\[?\s*{n}\s*\.\s*([^\n\r]+(?:\n[^\n\r]+){{0,2}})',
            rf'(?:^|\n)\s*\[?\s*Section\s+{n}\s*\.\s*([^\n\r]+(?:\n[^\n\r]+){{0,2}})',
            rf'(?:^|\n)\s*\[?\s*Article\s+{n}\s*\.\s*([^\n\r]+(?:\n[^\n\r]+){{0,2}})',
            rf'\[\s*(?:Section|Article)?\s*{n}\b[^\].]*?(?:omitted|repealed|rep\.|substituted)[^\]]*?\]',
        ]
        
        found = None
        for p in pats:
            m = re.search(p, full_text, re.IGNORECASE)
            if m:
                found = m.group(0).strip().replace('\n', ' ')
                break
                
        if found:
            act_evidence.append((n, found))
        else:
            no_evidence.append(n)
            
    print(f"Found explicit statutory evidence in text for: {len(act_evidence)}/{len(missing_nums)}")
    for n, ev in act_evidence[:15]:
        print(f"  Sec/Art {n}: {ev[:120]}...")
    if len(act_evidence) > 15:
        print(f"  ... and {len(act_evidence)-15} more with verified statutory text.")
        
    print(f"No direct evidence found for: {len(no_evidence)} sections: {no_evidence}")
    results[act_code] = {
        "missing_count": len(missing_nums),
        "with_evidence": len(act_evidence),
        "no_evidence": no_evidence,
        "sample_evidence": act_evidence[:5]
    }
