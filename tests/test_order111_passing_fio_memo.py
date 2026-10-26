"""
tests/test_order111_passing_fio_memo.py

ORDER 1.11 - ITEM 4:
Produces and verifies a legal research memorandum for the FIO s.22 query that passes
the ground-truth verification gate with the system disputed banner.
"""

import os
import sys
import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from legal_ai.verification.memo_verifier import MemoVerifier, attach_system_disputed_banner


def test_fio_s22_memo_passes_with_system_disputed_banner():
    memo_body = """## RESEARCH NOTE: Appeal Procedure Under Section 22 of the Financial Institutions Ordinance, 2001

### 1. Statutory Right of Appeal and Limitation Period

Section 22(1) of the Financial Institutions Ordinance, 2001 provides:

> Subject to sub-section (2), any person aggrieved by any judgment, decree, sentence, or final order passed by a Banking Court may, within thirty days of such judgment, decree, sentence or final order prefer an appeal to the High Court.

Under Section 22(1) of the Financial Institutions Ordinance, 2001, any aggrieved party may prefer an appeal within thirty days.

### 2. Notice Requirements to Respondent

Section 22(2) of the Financial Institutions Ordinance, 2001 provides:

> The appellant shall give notice of the filing of the appeal in accordance with the provisions of Order XLIII Rule 3 of the Code of Civil Procedure (Act V of 1908) to the respondent who may appear before the Banking Court to contest admission of the appeal on the date fixed for hearing.

Under Section 22(2) of the Financial Institutions Ordinance, 2001, notice of appeal is governed by the prescribed procedural rules.

### 3. Admission, Security, and Conditional Stay Requirements

Section 22(3) of the Financial Institutions Ordinance, 2001 provides:

> The High Court shall at the stage of admission of the appeal, or at any time thereafter either suo motu or on the application of the decree holder, decide by means of a reasoned order whether the appeal is to be admitted in part or in whole depending on the facts and circumstances of the case, and as to the security to be furnished by the appellant:
> Provided that the admission of the appeal shall not per se operate as a stay, and no shall any stay be granted therein unless the decree-holder has been given an opportunity of being heard and unless the appellant deposits in cash with the High Court an amount equivalent to the decretal amount inclusive of costs, or in the case of an appeal other than an appeal against an interim decree, at the discretion of the High Court furnishes security equal in value to such amount; and in the event of a stay being granted for a part of the decretal amount only, the requirement for a deposit in cash or furnishing of security shall stand reduced accordingly.

Under Section 22(3) of the Financial Institutions Ordinance, 2001, admission does not operate as an automatic stay without deposit or security.

### 4. Bench Composition and Statutory Disposition Window

Section 22(4) of the Financial Institutions Ordinance, 2001 provides:

> An appeal under sub-section (1) shall be heard by a bench of not less that two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission.

Under Section 22(4) of the Financial Institutions Ordinance, 2001, the appeal must be heard by a Division Bench and decided within ninety days.

### 5. Appeals from Ex-Parte Decrees

Section 22(5) of the Financial Institutions Ordinance, 2001 provides:

> An appeal may be preferred under this section from a decree passed ex-parte.

Under Section 22(5) of the Financial Institutions Ordinance, 2001, an appeal lies directly from an ex-parte decree.

### 6. Interlocutory Appeal Bar and Exceptions

Section 22(6) of the Financial Institutions Ordinance, 2001 provides:

> No appeal, review or revision shall lie against an order accepting or rejecting an application for leave to defend, or any interlocutory order of the Banking Court which does not dispose of the entire case before the Banking Court other than an order passed under sub-section (11) of section 15 [or sub-section (13) of section 15A] or sub-section (7) of section 19.

Under Section 22(6) of the Financial Institutions Ordinance, 2001, interlocutory appeals are strictly barred except for specific orders under Section 15, Section 15A, or Section 19.

### 7. Automatic Lapse of Stay Orders

Section 22(7) of the Financial Institutions Ordinance, 2001 provides:

> Any order of stay of execution of a decree passed under sub-section (2) shall automatically lapse on the expiry of six months from the date of the order whereupon the amount deposited in Court shall be paid over to the decree-holder or the decree-holder may enforce the security furnished by the judgment-debtor.

Under Section 22(7) of the Financial Institutions Ordinance, 2001, any stay of execution automatically lapses after six months.
"""

    bannered = attach_system_disputed_banner(memo_body, [{"provision": "FIO_2001_SEC_22"}])
    verifier = MemoVerifier()
    res = verifier.verify_memo(bannered, is_system_rendered=True)
    assert res["passed"] is True, f"Expected PASS, but got failures: {res.get('failures')}"
    assert res["verdict"] == "ACCEPTED"
    assert res["total_failures"] == 0
    assert res["quotes_failed"] == 0
    assert res["statutes_failed"] == 0
    assert res["cases_failed"] == 0
