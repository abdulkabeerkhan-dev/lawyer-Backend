"""
scripts/fix_fio_s22_verbatim.py

Re-extracts FIO Section 22 verbatim as printed in fio_2001.pdf (Pages 23-24).
Preserves all original printed typographical features:
  - 'bench of not less that two Judges' (not 'less than')
  - '(Act V of 1908)' (without added comma)
  - 'and no shall any stay be granted therein' (as printed)
  - 'amountI_ and in the event' (as printed)
Moves any corrections to a dedicated 'proposed_corrections' field.
"""

import os
import sys
import json
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIO_JSON = os.path.join(REPO_DIR, "data", "unified_statutes", "FIO_2001.json")

# Verbatim text exactly as printed in official PDF text layer (fio_2001.pdf pages 23-24)
VERBATIM_FIO_S22_TEXT = """22. Appeal. (1) Subject to sub-section (2), any person aggrieved by any judgment, decree, sentence, or final order passed by a Banking Court may, within thirty days of such judgment, decree, sentence or final order prefer an appeal to the High Court.
(2) The appellant shall give notice of the filing of the appeal in accordance with the provisions of Order XLIII Rule 3 of the Code of Civil Procedure (Act V of 1908) to the respondent who may appear before the Banking Court to contest admission of the appeal on the date fixed for hearing.
(3) The High Court shall at the stage of admission of the appeal, or at any time thereafter either suo motu or on the application of the decree holder, decide by means of a reasoned order whether the appeal is to be admitted in part or in whole depending on the facts and circumstances of the case, and as to the security to be furnished by the appellant:
Provided that the admission of the appeal shall not per se operate as a stay, and no shall any stay be granted therein unless the decree-holder has been given an opportunity of being heard and unless the appellant deposits in cash with the High Court an amount equivalent to the decretal amount inclusive of costs, or in the case of an appeal other than an appeal against an interim decree, at the discretion of the High Court furnishes security equal in value to such amountI_ and in the event of a stay being granted for a part of the decretal amount only, the requirement for a deposit in cash or furnishing of security shall stand reduced accordingly.
(4) An appeal under sub-section (1) shall be heard by a bench of not less that two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission.
(5) An appeal may be preferred under this section from a decree passed ex-parte.
(6) No appeal, review or revision shall lie against an order accepting or rejecting an application for leave to defend, or any interlocutory order of the Banking Court which does not dispose of the entire case before the Banking Court other than an order passed under sub-section (11) of section 15 1[or sub-section (13) of section 15A] or sub-section (7) of section 19.
(7) Any order of stay of execution of a decree passed under sub-section (2) shall automatically lapse on the expiry of six months from the date of the order whereupon the amount deposited in Court shall be paid over to the decree-holder or the decree-holder may enforce the security furnished by the judgment-debtor."""

PROPOSED_CORRECTIONS = [
    {
        "provision": "FIO_2001_SEC_22(4)",
        "printed_verbatim": "bench of not less that two Judges",
        "proposed_correction": "bench of not less than two Judges",
        "rationale": "Apparent typographical error ('that' for 'than') in official Gazette print layer."
    },
    {
        "provision": "FIO_2001_SEC_22(3) Proviso",
        "printed_verbatim": "and no shall any stay be granted",
        "proposed_correction": "and nor shall any stay be granted",
        "rationale": "Apparent typographical error ('no' for 'nor') in official Gazette print layer."
    },
    {
        "provision": "FIO_2001_SEC_22(3) Proviso",
        "printed_verbatim": "such amountI_ and in the event",
        "proposed_correction": "such amount, and in the event",
        "rationale": "OCR/print artifact 'amountI_' for 'amount,' in Gazette text layer."
    },
    {
        "provision": "FIO_2001_SEC_22(7)",
        "printed_verbatim": "passed under sub-section (2)",
        "proposed_correction": "passed under sub-section (3)",
        "rationale": "Cross-reference anomaly in statute text: sub-section (2) governs notice of appeal, whereas stay and security are governed by sub-section (3). Reported decisions address this anomaly."
    }
]

def main():
    print("=" * 110)
    print("RE-EXTRACTING FIO SECTION 22 VERBATIM AS PRINTED")
    print("=" * 110)

    with open(FIO_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    target_idx = -1
    for idx, r in enumerate(data):
        if r.get("canonical_id") == "FIO_2001_SEC_22":
            target_idx = idx
            break

    if target_idx == -1:
        print("Error: FIO_2001_SEC_22 not found in FIO_2001.json")
        sys.exit(1)

    rec = data[target_idx]
    old_text = rec.get("text", "")
    old_hash = rec.get("content_hash", "")

    # Update record
    rec["text"] = VERBATIM_FIO_S22_TEXT
    new_hash = hashlib.sha256(VERBATIM_FIO_S22_TEXT.encode("utf-8")).hexdigest()
    rec["content_hash"] = new_hash
    rec["proposed_corrections"] = PROPOSED_CORRECTIONS
    rec["source_pdf"] = "data/official_pdfs/fio_2001.pdf"
    rec["source_pages"] = [23, 24]
    rec["disputed_reason"] = "Text not yet checked against page images by a human."

    data[target_idx] = rec

    with open(FIO_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Old Content Hash: {old_hash}")
    print(f"New Content Hash: {new_hash}")
    print(f"Words: {len(VERBATIM_FIO_S22_TEXT.split())} words")
    print("\nProposed Corrections Recorded in Record:")
    for pc in PROPOSED_CORRECTIONS:
        print(f"  [{pc['provision']}]")
        print(f"    Printed:  '{pc['printed_verbatim']}'")
        print(f"    Proposed: '{pc['proposed_correction']}'")
        print(f"    Reason:   {pc['rationale']}")

    print("\nVerbatim Text First 200 Chars:")
    print(repr(VERBATIM_FIO_S22_TEXT[:200]))
    print("\nVerbatim Text Last 200 Chars:")
    print(repr(VERBATIM_FIO_S22_TEXT[-200:]))
    print("=" * 110)

if __name__ == "__main__":
    main()
