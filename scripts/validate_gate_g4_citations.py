import os
import sys
import json
import re
from pathlib import Path
from collections import Counter

ROOT_DIR = Path(r"d:\lawyer-Backend")
V3_STAGING_DIR = ROOT_DIR / "data" / "statutes_v3_staging"
REPORTS_DIR = ROOT_DIR / "reports"

def run_citation_check():
    print("=" * 70)
    print("GATE G4: CITATION CHECK (judgments_v1.statutes vs v3 + legacy)")
    print("=" * 70)

    # 1. Collect all canonical IDs and sub-clause IDs in v3 staging
    v3_ids = set()
    v3_base_ids = set()
    total_staging_files = 0
    for f in V3_STAGING_DIR.glob("*.json"):
        total_staging_files += 1
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    for r in data:
                        cid = r.get("canonical_id")
                        if cid:
                            v3_ids.add(cid)
                            # Also track base provision (e.g. FIO_2001_SEC_2 from FIO_2001_SEC_2_g)
                            parts = cid.split("_")
                            if len(parts) >= 4:
                                base_id = "_".join(parts[:4])
                                v3_base_ids.add(base_id)
        except Exception as e:
            print(f"Error reading {f.name}: {e}")

    print(f"Loaded {len(v3_ids):,} unique canonical IDs across {total_staging_files} staging files.")

    # 2. Load distinct citations from judgments_v1
    judgments_statutes_path = REPORTS_DIR / "judgments_v1_distinct_statutes.json"
    if not judgments_statutes_path.exists():
        print(f"ERROR: {judgments_statutes_path} not found!")
        return

    with open(judgments_statutes_path, "r", encoding="utf-8") as fp:
        jdata = json.load(fp)

    citations = jdata["statutes"]
    total_distinct = len(citations)
    total_occurrences = sum(citations.values())

    print(f"Total distinct citations in judgments_v1: {total_distinct:,}")
    print(f"Total citation occurrences: {total_occurrences:,}")

    # 3. Categorize and Resolve
    directly_resolved = {}
    alias_resolved = {}
    unresolved = {}
    proposed_aliases = {}

    # Common patterns
    re_const_sec = re.compile(r'^CONST_1973_SEC_(\d+[A-Z]?)$')
    re_const_const = re.compile(r'^(CONST_1973_ART_\d+[A-Z]?)CONSTITUTIONAL$')
    re_qso_sec = re.compile(r'^QSO_1984_SEC_(\d+[A-Z]?)$')
    re_police_sec = re.compile(r'^POLICE_ORDER_2002_SEC_(\d+[A-Z]?)$')
    re_cpc_ord = re.compile(r'^CPC_1908_O_([A-Za-z0-9]+)_R_(\d+[A-Za-z]?)$', re.IGNORECASE)
    re_hyphen = re.compile(r'^([A-Z0-9_]+_SEC_\d+)([A-Z])$')
    re_penal = re.compile(r'^([A-Z0-9_]+_SEC_\d+)PENAL$')
    re_clause_num = re.compile(r'^([A-Z0-9_]+_SEC_\d+)(\d)$')
    re_ppc_clause = re.compile(r'^(PPC_1860_SEC_\d+)([A-Z])$')

    for cit, count in citations.items():
        # Case A: Direct match
        if cit in v3_ids:
            directly_resolved[cit] = count
            continue

        # Case B: Alias transformations
        target_id = None
        uncertain = False
        reason = ""

        # 1. Constitution SEC -> ART
        m_csec = re_const_sec.match(cit)
        if m_csec:
            cand = f"CONST_1973_ART_{m_csec.group(1)}"
            if cand in v3_ids:
                target_id = cand
                reason = "Constitution Article labeled as Section in judgment extractor"

        # 2. Constitution CONSTITUTIONAL suffix
        if not target_id:
            m_cconst = re_const_const.match(cit)
            if m_cconst:
                cand = m_cconst.group(1)
                if cand in v3_ids:
                    target_id = cand
                    reason = "Stripped trailing CONSTITUTIONAL metadata suffix"

        # 3. QSO SEC -> ART
        if not target_id:
            m_qsec = re_qso_sec.match(cit)
            if m_qsec:
                cand = f"QSO_1984_ART_{m_qsec.group(1)}"
                if cand in v3_ids:
                    target_id = cand
                    reason = "Qanun-e-Shahadat Order Article labeled as Section in judgment extractor"

        # 4. Police Order SEC -> ART
        if not target_id:
            m_psec = re_police_sec.match(cit)
            if m_psec:
                cand = f"POLICE_ORDER_2002_ART_{m_psec.group(1)}"
                if cand in v3_ids:
                    target_id = cand
                    reason = "Police Order Article labeled as Section in judgment extractor"

        # 5. CPC Orders (O_VII_R_11 -> ORD_VII_R_11)
        if not target_id:
            m_cord = re_cpc_ord.match(cit)
            if m_cord:
                cand = f"CPC_1908_ORD_{m_cord.group(1).upper()}_R_{m_cord.group(2).upper()}"
                if cand in v3_ids:
                    target_id = cand
                    reason = "CPC Order rule notation unified (O_ -> ORD_)"

        # 6. Hyphenated sections (e.g. CRPC_1898_SEC_382B -> CRPC_1898_SEC_382-B)
        if not target_id:
            m_hyp = re_hyphen.match(cit)
            if m_hyp:
                cand = f"{m_hyp.group(1)}-{m_hyp.group(2)}"
                if cand in v3_ids:
                    target_id = cand
                    reason = "Hyphenated section suffix matched"

        # 7. Metadata PENAL suffix (e.g. PPC_1860_SEC_302PENAL -> PPC_1860_SEC_302)
        if not target_id:
            m_pen = re_penal.match(cit)
            if m_pen:
                cand = m_pen.group(1)
                if cand in v3_ids:
                    target_id = cand
                    reason = "Stripped trailing PENAL metadata suffix"

        # 8. Subsection digits concatenated without parenthesis (e.g. CRPC_1898_SEC_4972 -> CRPC_1898_SEC_497)
        if not target_id:
            m_cnum = re_clause_num.match(cit)
            if m_cnum:
                cand = m_cnum.group(1)
                if cand in v3_ids:
                    target_id = cand
                    reason = f"Concatenated subsection ({m_cnum.group(2)}) mapped to base section"

        # 9. PPC sub-clause (e.g. PPC_1860_SEC_302B -> PPC_1860_SEC_302_b or PPC_1860_SEC_302)
        if not target_id:
            m_ppc = re_ppc_clause.match(cit)
            if m_ppc:
                cand_base = m_ppc.group(1)
                cand_sub = f"{m_ppc.group(1)}_{m_ppc.group(2).lower()}"
                if cand_sub in v3_ids:
                    target_id = cand_sub
                    reason = "PPC sub-clause resolved"
                elif cand_base in v3_ids:
                    target_id = cand_base
                    reason = "PPC provision resolved to base section"

        # 10. Check base ID in v3
        if not target_id:
            if cit in v3_base_ids:
                target_id = cit
                reason = "Base section of partitioned sub-clauses"

        if target_id:
            alias_resolved[cit] = (target_id, count, reason)
            proposed_aliases[cit] = target_id
        else:
            # Categorize why it is unresolved
            cat = "unknown"
            if cit.startswith("CRPC_1898_SEC_302"):
                cat = "erroneous_extractor_artifact (PPC 302 cross-pollinated into CrPC)"
            elif cit.startswith("CONST_1973_ART_98") or cit.startswith("CONST_1973_SEC_98"):
                cat = "historic_constitution_1962 (Article 98 was writ jurisdiction)"
            elif "ORDER" in cit or "RULE" in cit:
                cat = "procedural_court_rules_or_orders"
            elif any(prov in cit for prov in ["PUNJAB", "SINDH", "BALOCHISTAN", "KPK", "NWFP"]):
                cat = "provincial_statute (outside federal Pakistan Code)"
            elif "_REPEALED" in cit:
                cat = "repealed_statute"
            else:
                cat = "unmatched_statute_or_extraction_noise"

            unresolved[cit] = (count, cat)

    # 4. Compute statistics
    dir_count = len(directly_resolved)
    dir_occ = sum(directly_resolved.values())
    alias_count = len(alias_resolved)
    alias_occ = sum(x[1] for x in alias_resolved.values())
    unres_count = len(unresolved)
    unres_occ = sum(x[0] for x in unresolved.values())

    resolved_distinct = dir_count + alias_count
    resolved_occ = dir_occ + alias_occ

    print("\n" + "=" * 70)
    print("GATE G4 RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total Distinct Citations in judgments_v1 : {total_distinct:,}")
    print(f"Total Occurrences in judgments_v1        : {total_occurrences:,}")
    print(f"Directly Resolved Distinct              : {dir_count:,} ({dir_count/total_distinct:.1%})")
    print(f"Directly Resolved Occurrences           : {dir_occ:,} ({dir_occ/total_occurrences:.1%})")
    print(f"Alias Resolved Distinct                 : {alias_count:,} ({alias_count/total_distinct:.1%})")
    print(f"Alias Resolved Occurrences              : {alias_occ:,} ({alias_occ/total_occurrences:.1%})")
    print(f"TOTAL RESOLVED DISTINCT                 : {resolved_distinct:,} ({resolved_distinct/total_distinct:.1%})")
    print(f"TOTAL RESOLVED OCCURRENCES              : {resolved_occ:,} ({resolved_occ/total_occurrences:.1%})")
    print(f"Unresolved Distinct                     : {unres_count:,} ({unres_count/total_distinct:.1%})")
    print(f"Unresolved Occurrences                  : {unres_occ:,} ({unres_occ/total_occurrences:.1%})")

    # Sort unresolved by count
    top_unresolved = sorted(unresolved.items(), key=lambda x: x[1][0], reverse=True)[:50]
    print("\nTop 20 Unresolved Citations:")
    for cit, (cnt, cat) in top_unresolved[:20]:
        print(f"  {cit:45}: {cnt:,} ({cat})")

    # Save report
    report_data = {
        "summary": {
            "total_distinct_citations": total_distinct,
            "total_citation_occurrences": total_occurrences,
            "directly_resolved_distinct": dir_count,
            "directly_resolved_occurrences": dir_occ,
            "alias_resolved_distinct": alias_count,
            "alias_resolved_occurrences": alias_occ,
            "total_resolved_distinct": resolved_distinct,
            "total_resolved_occurrences": resolved_occ,
            "unresolved_distinct": unres_count,
            "unresolved_occurrences": unres_occ
        },
        "top_unresolved": [
            {"citation": cit, "count": cnt, "category": cat}
            for cit, (cnt, cat) in top_unresolved
        ],
        "proposed_aliases_count": len(proposed_aliases),
        "proposed_aliases": proposed_aliases
    }

    report_out = REPORTS_DIR / "citation_reconciliation_report.json"
    with open(report_out, "w", encoding="utf-8") as fp:
        json.dump(report_data, fp, indent=2, ensure_ascii=False)

    print(f"\nSaved full report to {report_out}")

if __name__ == "__main__":
    run_citation_check()
