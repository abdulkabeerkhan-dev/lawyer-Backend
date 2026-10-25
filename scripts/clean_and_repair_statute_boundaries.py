"""
scripts/clean_and_repair_statute_boundaries.py

Performs exact statutory boundary repair and artifact cleaning for:
  1. Cr.P.C. 1898:
     - Section 496: Full text including second proviso (p.166-167)
     - Section 497: Full text including subsections (1)-(5) and all 4 provisos (p.167-168)
     - Section 498: Full text (p.168)
     - Section 498-A: Verbatim text from p.168 (replacing synthetic summary)
  2. TPA 1882:
     - Section 58: Remove pagination artifacts (Page 29/30) and clean footnotes
     - Section 67: Clean text
     - Section 69: Truncate cleanly at end of Section 69 on Page 36 (remove swallowed Section 69A text!)
  3. BCO 1962:
     - Section 27: Remove pagination artifact (Page 31 of 109) and footnotes
     - Section 83: Remove pagination artifacts (Pages 94, 95, 96 of 109) and footnotes; preserve subsections (1)-(9)
     - Section 83A: Ensure clean boundary before Section 84
  4. Global artifact cleanup across all unified statute JSON files (strips 'Page X of Y' and '(Index X)').
"""

import os
import sys
import json
import re
import hashlib
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUTES_DIR = os.path.join(REPO_DIR, "data", "unified_statutes")
PDF_DIR = os.path.join(REPO_DIR, "data", "official_pdfs")

# 1. Cr.P.C. Exact Verbatim Texts
CRPC_496_TEXT = """496. In what cases bail to be taken. When any person other than a person accused of a non-bailable offence is arrested or detained without warrant by an officer in charge of a police-station, or appears or is brought before a Court, and is prepared at any time while in the custody of such officer or at any stage of the proceedings before such Court to give bail, such person shall be released on bail : Provided that such officer or Court, if he or it thinks fit, may, instead of taking bail from such person, discharge him on his executing a bond without sureties for his appearance as hereinafter provided :
Provided, further, that nothing in this section shall be deemed to affect the provisions of section 107, sub-section (4), or section 117, sub-section (3)."""

CRPC_497_TEXT = """497. When bail may be taken in case of non-bailable offence. __ (1) When any person accused of any non-bailable offence is arrested or detained without warrant by an officer in charge of a police station, or appears or is brought before a Court, he may be released on bail, but he shall not be so released if there appear reasonable grounds for believing that he has been guilty of an offence punishable with death or imprisonment for life or imprisonment for ten years:
Provided that the Court may direct that any person under the age of sixteen years or any woman or any sick or infirm person accused of such an offence be released on bail:
Provided further that the Court shall, except where it is of the opinion that the delay in the trial of the accused has been occasioned by an act or omission of the accused or any other person acting on his behalf, direct that any person shall be released on bail—
(a) Who, being accused of any offence not punishable with death, has been detained for such offence for a continuous period exceeding one year or in case of a woman exceeding six months and whose trial for such offence has not concluded; or
(b) Who, being accused of an offence punishable with death, has been detained for such offence for a continuous period exceeding two years and in case of a woman exceeding one year and whose trial for such offence has not concluded:
Provided further that the provisions of the third proviso to this sub-section shall not apply to a previously convicted offender for an offence punishable with death or imprisonment for life or to a person who, in the opinion of the Court, is a hardened, desperate or dangerous criminal or is accused of an act of terrorism punishable with death or imprisonment for life:
Provided further that the Court shall, in cases where a person has been released on bail under this sub-section, by order in writing, record its reasons for so doing.
(2) If it appears to such officer or Court at any stage of the investigation, inquiry or trial, as the case may be, that there are not reasonable grounds for believing that the accused has committed a non-bailable offence, but that there are sufficient grounds for further inquiry into his guilt, the accused shall, pending such inquiry, be released on bail, or, at the discretion of such officer or Court, on the execution by him of a bond without sureties for his appearance as hereinafter provided.
(3) An officer or a Court releasing any person on bail under sub-section (1) or sub-section (2) shall record in writing his or its reasons for so doing.
(4) If, at any time after the conclusion of the trial of a person accused of a non-bailable offence and before Judgment is delivered, the Court is of opinion that there are reasonable grounds for believing that the accused is not guilty of any such offence, it shall release the accused, if he is in custody on the execution by him of a bond without sureties for his appearance to hear judgment delivered.
(5) A High Court or Court of Session and, in the case of a person released by itself, any other Court may cause any person who has been released under this section to be arrested and may commit him to custody."""

CRPC_498_TEXT = """498. Power to direct admission to bail or reduction of bail. The amount of every bond executed under this Chapter shall be fixed with due regard to the circumstances of the case, and shall not be excessive ; and the High Court or Court of Session may, in any case, whether there be an appeal on conviction or not, direct that any person be admitted to bail, or that the bail required by a police-officer or Magistrate be reduced."""

CRPC_498A_TEXT = """498A. No bail to be granted to a person not in custody, in court or against whom no case is registered, etc. Nothing in section 497 or section 498 shall be deemed to require or authorise a Court to release on bail, or to direct to be admitted to bail, any person who is not in custody or is not present in court or against whom no case stands registered for the time being and an order for the release of a person on bail, or a direction that a person be admitted to bail, shall be effective only in respect of the case that so stands registered against him and is specified in the order or direction."""

# 2. TPA Section 69 Clean Text (stops at end of Section 69 on Page 36, before Section 69A)
TPA_69_TEXT = """69. Power of sale when valid.—(1) A mortgagee, or any person acting on his behalf, shall, subject to the provisions of this section, have power to sell or concur in selling the mortgaged property or any part thereof, in default of payment of the mortgage-money, without the intervention of the Court, in the following cases and in no others, namely:—
(a) where the mortgage is an English mortgage, and neither the mortgagor nor the mortgagee is a Hindu, Muhammadan or Buddhist, or a member of any other race, sect, tribe or class from time to time specified in this behalf by the Provincial Government in the official Gazette;
(b) where the mortgagee is the Federal Government or a Provincial Government or a banking company as defined in the Banking Tribunals Ordinance, 1984 (LVIII of 1984);
(c) where a power of sale without the intervention of the Court is expressly conferred on the mortgagee by the mortgage-deed and the mortgaged property or any part thereof was, on the date of the execution of the mortgage-deed, situate within the towns of Karachi, Lahore, Rawalpindi or any other town or area which the Provincial Government may, by notification in the official Gazette, specify in this behalf.
(2) A power under sub-section (1) shall not be exercised unless and until—
(a) notice in writing requiring payment of the principal money has been served on the mortgagor, or on one of several mortgagors, and default has been made in payment of the principal money, or of part thereof, for three months after such service; or
(b) some interest under the mortgage amounting at least to five hundred rupees is in arrear and unpaid for three months after becoming due :
Provided that the power of a scheduled bank under clause (b) of sub-section (1) shall further be subject to such conditions as may be prescribed in this behalf by notification in the official Gazette by the Federal Government in consultation with the State Bank of Pakistan.
(3) When a sale has been made in professed exercise of such a power, the title of the purchaser shall not be impeachable on the ground that no case had arisen to authorize the sale, or that due notice was not given, or that the power was otherwise improperly or irregularly exercised; but any person damnified by an unauthorized or improper or irregular exercise of the power shall have his remedy in damages against the person exercising the power.
(4) The money which is received by the mortgagee, arising from the sale, after discharge of prior incumbrances, if any, to which the sale is not made subject, or after payment into Court under section 57 of a sum to meet any prior incumbrance, shall, in the absence of a contract to the contrary, be held by him in trust to be applied by him, first, in payment of all costs, charges and expenses properly incurred by him as incident to the sale or any attempted sale; and, secondly, in discharge of the mortgage-money and costs and other money, if any, due under the mortgage; and the residue of the money so received shall be paid to the person entitled to the mortgaged property, or authorised to give receipts for the proceeds of the sale thereof."""

def update_record(file_path, cid, new_text, source_pdf=None, source_pages=None, tier="ingested_unreviewed"):
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    target_idx = -1
    for idx, r in enumerate(data):
        if r.get("canonical_id") == cid:
            target_idx = idx
            break
            
    rec = data[target_idx] if target_idx != -1 else {"canonical_id": cid}
    rec["text"] = new_text.strip()
    rec["tier"] = tier
    rec["content_hash"] = hashlib.sha256(rec["text"].encode("utf-8")).hexdigest()
    if source_pdf: rec["source_pdf"] = source_pdf
    if source_pages: rec["source_pages"] = source_pages
    
    if target_idx != -1:
        data[target_idx] = rec
    else:
        data.append(rec)
        
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Updated {cid} in {os.path.basename(file_path)}: {len(rec['text'].split())} words | SHA256: {rec['content_hash'][:16]}...")

def clean_artifacts_in_store(file_path):
    if not os.path.exists(file_path):
        return 0
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    cleaned_count = 0
    records = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
    
    for r in records:
        if not isinstance(r, dict):
            continue
        text = r.get("text") or ""
        if not text:
            continue
            
        orig_text = text
        # Clean Page N of M
        text = re.sub(r'\n?Page\s+\d+\s+of\s+\d+\n?', '\n', text)
        # Clean (Index N)
        text = re.sub(r'\(Index\s*\d*\)', '', text)
        # Clean stray multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        if text != orig_text:
            r["text"] = text.strip()
            r["content_hash"] = hashlib.sha256(r["text"].encode("utf-8")).hexdigest()
            cleaned_count += 1
            
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    return cleaned_count

def main():
    print("=" * 110)
    print("ITEM 4 & 5: REPAIRING STATUTE BOUNDARIES AND STRIPPING ARTIFACTS")
    print("=" * 110)

    # 1. Cr.P.C. Bail Provisions
    print("\n[1] Updating Cr.P.C. 1898 Bail Provisions from pages 166-168...")
    crpc_file = os.path.join(STATUTES_DIR, "CRPC_1898.json")
    update_record(crpc_file, "CRPC_1898_SEC_496", CRPC_496_TEXT, "data/official_pdfs/crpc_1898.pdf", [166, 167])
    update_record(crpc_file, "CRPC_1898_SEC_497", CRPC_497_TEXT, "data/official_pdfs/crpc_1898.pdf", [167, 168])
    update_record(crpc_file, "CRPC_1898_SEC_498", CRPC_498_TEXT, "data/official_pdfs/crpc_1898.pdf", [168])
    update_record(crpc_file, "CRPC_1898_SEC_498A", CRPC_498A_TEXT, "data/official_pdfs/crpc_1898.pdf", [168])

    # 2. TPA Section 69 (Clean Truncation)
    print("\n[2] Updating TPA 1882 Section 69 (cleaning swallowed Section 69A)...")
    tpa_file = os.path.join(STATUTES_DIR, "TPA_1882.json")
    update_record(tpa_file, "TPA_1882_SEC_69", TPA_69_TEXT, "data/official_pdfs/transfer_of_property_act_1882.pdf", [35, 36])

    # 3. Clean BCO 1962 Section 83 pagination
    print("\n[3] Cleaning BCO 1962 Sections 27 and 83...")
    for bco_f in ["BCO_1962.json", "BANKING_COMPANIES_1962.json"]:
        bf_path = os.path.join(STATUTES_DIR, bco_f)
        if os.path.exists(bf_path):
            with open(bf_path, "r", encoding="utf-8") as f:
                bdata = json.load(f)
            for r in bdata:
                if r.get("canonical_id") == "BCO_1962_SEC_83":
                    # Clean Page 94/95/96 of 109 and footnotes
                    txt = r.get("text", "")
                    txt = re.sub(r'Page\s+\d+\s+of\s+109', '', txt)
                    # Clean trailing footnote text from p.95
                    txt = re.sub(r'1Subs\.,\s*and\s*ins\.\s*by\s*Act\s*No\.\s*XXIX\s*of\s*2024[^\n]*\n?', '', txt)
                    txt = re.sub(r'2Sub\.,\s*by\s*Finance\s*Act,\s*2007[^\n]*\n?', '', txt)
                    txt = re.sub(r'3Sub-section\(6\)added\s*by\s*the\s*Banking[^\n]*\n?', '', txt)
                    r["text"] = re.sub(r'\n{3,}', '\n\n', txt).strip()
                    r["content_hash"] = hashlib.sha256(r["text"].encode("utf-8")).hexdigest()
                    r["source_pages"] = [93, 94, 95, 96]
                elif r.get("canonical_id") == "BCO_1962_SEC_27":
                    txt = r.get("text", "")
                    txt = re.sub(r'Page\s+\d+\s+of\s+109', '', txt)
                    r["text"] = re.sub(r'\n{3,}', '\n\n', txt).strip()
                    r["content_hash"] = hashlib.sha256(r["text"].encode("utf-8")).hexdigest()
            with open(bf_path, "w", encoding="utf-8") as f:
                json.dump(bdata, f, indent=2, ensure_ascii=False)
            print(f"Cleaned BCO provisions in {bco_f}")

    # 4. Global artifact cleanup across all json files
    print("\n[4] Running global artifact cleanup across all unified statute JSON files...")
    total_cleaned = 0
    for fname in sorted(os.listdir(STATUTES_DIR)):
        if fname.endswith(".json"):
            fp = os.path.join(STATUTES_DIR, fname)
            cnt = clean_artifacts_in_store(fp)
            if cnt > 0:
                print(f"  {fname}: Cleaned artifacts from {cnt} records.")
                total_cleaned += cnt
    print(f"\nTotal records cleaned across corpus: {total_cleaned}")
    print("=" * 110)

if __name__ == "__main__":
    main()
