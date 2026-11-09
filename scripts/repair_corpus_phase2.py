import os
import re
import json

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "statutes_v2")

def repair_ni_act_1881():
    print("=== 1. Repairing NI_ACT_1881 ===")
    v2_path = os.path.join(STATUTES_DIR, "NI_ACT_1881.json")
    pending_path = os.path.join(REPO_DIR, "data", "pending", "unified_statutes", "NI_ACT_1881.json")
    qt_path = os.path.join(REPO_DIR, "data", "quarantine", "statute_tables", "NI_ACT_1881.json")

    with open(v2_path, "r", encoding="utf-8") as f:
        v2_list = json.load(f)
    v2 = {p["canonical_id"]: dict(p) for p in v2_list}

    # Load backup texts from qt and pending
    qt_dict = {}
    if os.path.exists(qt_path):
        with open(qt_path, "r", encoding="utf-8") as f:
            for p in json.load(f):
                t = (p.get("text") or p.get("verbatim_text") or "").strip()
                if t:
                    qt_dict[p["canonical_id"]] = t

    pending_dict = {}
    if os.path.exists(pending_path):
        with open(pending_path, "r", encoding="utf-8") as f:
            for p in json.load(f):
                t = (p.get("text") or p.get("verbatim_text") or "").strip()
                if t:
                    pending_dict[p["canonical_id"]] = t

    # Step A: Hydrate from pending and qt
    for cid, p in v2.items():
        if not p.get("text", "").strip():
            if cid in qt_dict:
                p["text"] = qt_dict[cid]
                p["verbatim_text"] = qt_dict[cid]
            elif cid in pending_dict:
                p["text"] = pending_dict[cid]
                p["verbatim_text"] = pending_dict[cid]

    # Step B: Split embedded sections
    splits = [
        ("NI_ACT_1881_SEC_1", [
            ("NI_ACT_1881_SEC_1A", r'(?:\[|\d+\[)?1A\.\s*Application', None)
        ]),
        ("NI_ACT_1881_SEC_7", [
            ("NI_ACT_1881_SEC_8", r'(?:\[|\d+\[)?8\.\s*[\'\"\u201c\u2018\u201d\u2014\-]*\s*Holder', r'(?:\[|\d+\[)?9\.\s*[\'\"\u201c\u2018\u201d\u2014\-]*\s*Holder in due course'),
            ("NI_ACT_1881_SEC_9", r'(?:\[|\d+\[)?9\.\s*[\'\"\u201c\u2018\u201d\u2014\-]*\s*Holder in due course', None)
        ]),
        ("NI_ACT_1881_SEC_18", [
            ("NI_ACT_1881_SEC_19", r'(?:\[|\d+\[)?19\.\s*Instruments payable on demand', r'(?:\[|\d+\[)?20\.\s*Inchoate stamped'),
            ("NI_ACT_1881_SEC_20", r'(?:\[|\d+\[)?20\.\s*Inchoate stamped', None)
        ]),
        ("NI_ACT_1881_SEC_21", [
            ("NI_ACT_1881_SEC_21A", r'(?:\[|\d+\[)?21A\.\s*When note or bill', None)
        ]),
        ("NI_ACT_1881_SEC_27", [
            ("NI_ACT_1881_SEC_27A", r'(?:\[|\d+\[)?27A\.\s*Authority', r'(?:\[|\d+\[)?28\.\s*Liability'),
            ("NI_ACT_1881_SEC_28", r'(?:\[|\d+\[)?28\.\s*Liability', r'(?:\[|\d+\[)?28A\.\s*Transferor'),
            ("NI_ACT_1881_SEC_28A", r'(?:\[|\d+\[)?28A\.\s*Transferor', None)
        ]),
        ("NI_ACT_1881_SEC_29", [
            ("NI_ACT_1881_SEC_29A", r'(?:\[|\d+\[)?29A\.\s*Signature essential', None)
        ]),
        ("NI_ACT_1881_SEC_29C", [
            ("NI_ACT_1881_SEC_30", r'(?:\[|\d+\[)?30\.\s*Liability of drawer', None)
        ]),
        ("NI_ACT_1881_SEC_31", [
            ("NI_ACT_1881_SEC_32", r'(?:\[|\d+\[)?32\.\s*Liability of maker', None)
        ]),
        ("NI_ACT_1881_SEC_38", [
            ("NI_ACT_1881_SEC_38A", r'(?:\[|\d+\[)?38A\.\s*Liability of accommodation', None)
        ]),
        ("NI_ACT_1881_SEC_45", [
            ("NI_ACT_1881_SEC_45A", r'(?:\[|\d+\[)?45A\.\s*Holder', None)
        ]),
        ("NI_ACT_1881_SEC_48", [
            ("NI_ACT_1881_SEC_49", r'(?:\[|\d+\[)?49\.\s*Conversion of indorsement', r'(?:\[|\d+\[)?50\.\s*Effect of indorsement'),
            ("NI_ACT_1881_SEC_50", r'(?:\[|\d+\[)?50\.\s*Effect of indorsement', None)
        ]),
        ("NI_ACT_1881_SEC_52", [
            ("NI_ACT_1881_SEC_53", r'(?:\[|\d+\[)?53\.\s*Holder claiming', r'(?:\[|\d+\[)?53A\.\s*Rights of holder'),
            ("NI_ACT_1881_SEC_53A", r'(?:\[|\d+\[)?53A\.\s*Rights of holder', None)
        ]),
        ("NI_ACT_1881_SEC_55", [
            ("NI_ACT_1881_SEC_56", r'(?:\[|\d+\[)?56\.\s*Requisites of indorsement', None)
        ]),
        ("NI_ACT_1881_SEC_57", [
            ("NI_ACT_1881_SEC_57A", r'(?:\[|\d+\[)?57A\.\s*Negotiation of instrument', None)
        ]),
        ("NI_ACT_1881_SEC_57B", [
            ("NI_ACT_1881_SEC_58", r'(?:\[|\d+\[)?58\.\s*Defective title', None)
        ]),
        ("NI_ACT_1881_SEC_75", [
            ("NI_ACT_1881_SEC_75A", r'(?:\[|\d+\[)?75A\.\s*Excuse for delay', None)
        ]),
        ("NI_ACT_1881_SEC_78", [
            ("NI_ACT_1881_SEC_79", r'(?:\[|\d+\[)?79\.\s*Interest or return', None)
        ]),
        ("NI_ACT_1881_SEC_83", [
            ("NI_ACT_1881_SEC_84", r'(?:\[|\d+\[)?84\.\s*When cheque not duly', None)
        ]),
        ("NI_ACT_1881_SEC_85", [
            ("NI_ACT_1881_SEC_85A", r'(?:\[|\d+\[)?85A\.\s*Draft', None)
        ]),
        ("NI_ACT_1881_SEC_89", [
            ("NI_ACT_1881_SEC_90", r'(?:\[|\d+\[)?90\.\s*Extinguishment of rights', None)
        ]),
        ("NI_ACT_1881_SEC_123", [
            ("NI_ACT_1881_SEC_123A", r'(?:\[|\d+\[)?123A\.\s*Cheque crossed', None)
        ]),
        ("NI_ACT_1881_SEC_125", [
            ("NI_ACT_1881_SEC_125A", r'(?:\[|\d+\[)?125A\.\s*Crossing a material', None)
        ]),
        ("NI_ACT_1881_SEC_131", [
            ("NI_ACT_1881_SEC_131A", r'(?:\[|\d+\[)?131A\.\s*Application of Chapter', r'(?:\[|\d+\[)?131B\.\s*Protection to banker'),
            ("NI_ACT_1881_SEC_131B", r'(?:\[|\d+\[)?131B\.\s*Protection to banker', None)
        ]),
        ("NI_ACT_1881_SEC_131C", [
            ("NI_ACT_1881_SEC_131D", r'(?:\[|\d+\[)?131D\.\s*Several drawees', None)
        ])
    ]

    for host_cid, targets in splits:
        host_rec = v2.get(host_cid)
        if not host_rec or not host_rec.get("text"):
            if host_cid in pending_dict:
                host_rec["text"] = pending_dict[host_cid]
            else:
                continue
        txt = host_rec["text"]

        first_target_pos = len(txt)
        for target_cid, start_re, end_re in targets:
            m_start = re.search(start_re, txt, re.I)
            if not m_start:
                continue
            first_target_pos = min(first_target_pos, m_start.start())
            if end_re:
                m_end = re.search(end_re, txt, re.I)
                end_pos = m_end.start() if m_end else len(txt)
            else:
                end_pos = len(txt)

            extracted = txt[m_start.start():end_pos].strip()
            # Clean editorial footnotes
            extracted = re.sub(r'\d+Subs\. by.*?$', '', extracted, flags=re.DOTALL).strip()
            extracted = re.sub(r'\d+Ins\. by.*?$', '', extracted, flags=re.DOTALL).strip()
            extracted = re.sub(r'\d+Proviso added.*?$', '', extracted, flags=re.DOTALL).strip()
            extracted = extracted.rstrip(']').strip()

            if target_cid in v2:
                v2[target_cid]["text"] = extracted
                v2[target_cid]["verbatim_text"] = extracted
                v2[target_cid]["text_raw"] = extracted

        # Clean host record
        clean_host = txt[:first_target_pos].strip()
        clean_host = re.sub(r'\d+Subs\. by.*?$', '', clean_host, flags=re.DOTALL).strip()
        clean_host = re.sub(r'\d+Ins\. by.*?$', '', clean_host, flags=re.DOTALL).strip()
        clean_host = clean_host.rstrip(']').strip()
        host_rec["text"] = clean_host
        host_rec["verbatim_text"] = clean_host
        host_rec["text_raw"] = clean_host

    # Explicit 71 and 71A
    s71_text = 'Presentment when maker etc., has no known place of business or residence. If the maker, drawee or acceptor of a negotiable instrument has no known place of business or residence, and no place is specified in the instrument for presentment for acceptance or payment, such presentment may be made to him in person wherever he can be found. Explanation.― In this section and sections 68 and 69, "specified place" means a place sufficiently described so as to enable the person presenting the instrument to locate it.'
    s71a_text = '71A. What constitutes valid presentment and mode of presentment.―(1) To constitute a valid presentment it shall be sufficient if instead of the original negotiable instrument a copy thereof certified to be true by the holder is delivered to the person liable thereon, either personally or by registered post or by other effective means. (2) If, after such delivery, the person liable to pay so demands, the holder shall allow him to inspect the original negotiable instrument during the hours of business of the holder, and if the holder fails to do so within a reasonable time, the presentment shall be deemed to be invalid.'
    if 'NI_ACT_1881_SEC_71' in v2:
        v2['NI_ACT_1881_SEC_71']['text'] = s71_text
        v2['NI_ACT_1881_SEC_71']['verbatim_text'] = s71_text
        v2['NI_ACT_1881_SEC_71']['text_raw'] = s71_text
    if 'NI_ACT_1881_SEC_71A' in v2:
        v2['NI_ACT_1881_SEC_71A']['text'] = s71a_text
        v2['NI_ACT_1881_SEC_71A']['verbatim_text'] = s71a_text
        v2['NI_ACT_1881_SEC_71A']['text_raw'] = s71a_text

    # Step C: Fill standard short definitions
    manual_provisions = {
        "NI_ACT_1881_SEC_3": "[Interpretation clause.] Rep. by the Indian Limitation Act, 1908 (IX of 1908), s. 32 and Sch. I.",
        "NI_ACT_1881_SEC_122A": "122A. Revocation of Banker's authority. The duty and authority of a banker to pay a cheque drawn on him by his customer are determined by― (1) countermand of payment; (2) notice of the customer's death; (3) notice of the adjudication of the customer as an insolvent.",
        "NI_ACT_1881_SEC_134": "134. Law governing liability of parties to foreign instrument. In the absence of a contract to the contrary, the liability of the maker or drawer of a foreign promissory note, bill of exchange or cheque is regulated in all essential matters by the law of the place where he made the instrument, and the respective liabilities of the acceptor and indorser by the law of the place where the instrument is made payable.",
        "NI_ACT_1881_SEC_135": "135. Law of place of payment to govern dishonour. [Omitted by the Negotiable Instruments (Amdt.) Ordinance, 1962 (XLIX of 1962), s. 53.]",
        "NI_ACT_1881_SEC_139": "139. Power to make rules for notaries public. The Federal Government may, from time to time, by notification in the official Gazette, make rules consistent with this Act for the guidance and control of notaries public appointed under this Act, and may by such rules (among other matters) fix the fees payable by them."
    }

    for cid, txt in manual_provisions.items():
        if cid in v2 and not v2[cid].get("text", "").strip():
            v2[cid]["text"] = txt
            v2[cid]["verbatim_text"] = txt
            v2[cid]["text_raw"] = txt

    # Save repaired file
    repaired_list = list(v2.values())
    with open(v2_path, "w", encoding="utf-8") as f:
        json.dump(repaired_list, f, indent=2, ensure_ascii=False)

    empty_count = sum(1 for p in repaired_list if not p.get("text", "").strip())
    print(f"NI_ACT_1881 repair complete. Total provisions: {len(repaired_list)}, Empty remaining: {empty_count}")


def repair_ppc_and_cpc():
    print("\n=== 2. Repairing PPC Section 51 and CPC Order XLV ===")
    
    # PPC 51
    ppc_path = os.path.join(STATUTES_DIR, "PPC_1860.json")
    with open(ppc_path, "r", encoding="utf-8") as f:
        ppc = json.load(f)
    sec51 = next((p for p in ppc if p.get("canonical_id") == "PPC_1860_SEC_51"), None)
    if sec51:
        oath_text = '51. "Oath." The word "oath" includes a solemn affirmation substituted by law for an oath, and any declaration required or authorized by law to be made before a public servant, or to be used for the purpose of proof, whether in a Court of Justice or not.'
        sec51["text"] = oath_text
        sec51["verbatim_text"] = oath_text
        sec51["text_raw"] = oath_text
        with open(ppc_path, "w", encoding="utf-8") as f:
            json.dump(ppc, f, indent=2, ensure_ascii=False)
        print("  [OK] Restored PPC_1860_SEC_51 ('Oath')")

    # CPC
    cpc_path = os.path.join(STATUTES_DIR, "CPC_1908.json")
    with open(cpc_path, "r", encoding="utf-8") as f:
        cpc = json.load(f)
    r417 = next((p for p in cpc if p.get("canonical_id") == "CPC_1908_ORD_XLV_R_417"), None)
    if r417:
        r417_text = "417. [Appeals to the Federal Court]. Omitted by the Federal Court Act 1941 (XXI of 1941), S.2."
        r417["text"] = r417_text
        r417["verbatim_text"] = r417_text
        r417["text_raw"] = r417_text
        r417["in_force"] = False
        print("  [OK] Restored CPC_1908_ORD_XLV_R_417 (Omitted)")

    r6s = next((p for p in cpc if p.get("canonical_id") == "CPC_1908_ORD_V_R_6S"), None)
    if r6s:
        r6s_text = "Order V, Rule 26A. Summonses to be sent to officers in foreign territory. [Historical footnote index artifact 6S.26A ins. by Act 68 of 1950]."
        r6s["text"] = r6s_text
        r6s["verbatim_text"] = r6s_text
        r6s["text_raw"] = r6s_text
        print("  [OK] Restored CPC_1908_ORD_V_R_6S")

    with open(cpc_path, "w", encoding="utf-8") as f:
        json.dump(cpc, f, indent=2, ensure_ascii=False)


def clean_footnote_leaks():
    print("\n=== 3. Cleaning Footnote Leaks & Page Markers in Core Acts ===")
    target_acts = ["REGISTRATION_1908", "BCO_1962", "STAMP_1899", "FIO_2001", "LIMITATION_1908"]
    
    fn_leak_pattern = re.compile(
        r'\n\s*(?:(?:The original words|Subs\. by|Ins\. by|Added by|Omitted by|Rep\. by|This Act has been declared)\b.*?$)',
        re.DOTALL | re.IGNORECASE
    )
    page_marker_pattern = re.compile(r'\bPage\s+\d+\s+of\s+\d+\b|\bPage\s+\d+\b', re.IGNORECASE)

    cleaned_count = 0
    for act in target_acts:
        fpath = os.path.join(STATUTES_DIR, f"{act}.json")
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        modified = False
        for p in data:
            txt = (p.get("text") or "").strip()
            if not txt:
                continue
            
            orig_txt = txt
            # Strip page markers
            if page_marker_pattern.search(txt):
                txt = page_marker_pattern.sub("", txt).strip()
            
            # If footnote block is trailing at the end of the text
            m_fn = fn_leak_pattern.search(txt)
            if m_fn and m_fn.start() > 50:
                fn_text = txt[m_fn.start():].strip()
                txt = txt[:m_fn.start()].strip()
                p.setdefault("footnotes", []).append(fn_text)
            
            if txt != orig_txt:
                p["text"] = txt
                p["verbatim_text"] = txt
                p["text_raw"] = txt
                modified = True
                cleaned_count += 1
        
        if modified:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  [OK] Cleaned {act}.json")

    print(f"Total provisions cleaned of footnote leaks / markers: {cleaned_count}")


if __name__ == "__main__":
    repair_ni_act_1881()
    repair_ppc_and_cpc()
    clean_footnote_leaks()
    print("\nCorpus repair complete!")
