# ADVOCATE HUMAN REVIEW SHEET: FIO SECTION 22 APPELLATE PROVISION

**Target Provision:** Section 22, Financial Institutions (Recovery of Finances) Ordinance, 2001  
**Canonical ID:** `FIO_2001_SEC_22`  
**Current Tier:** `disputed`  
**Official Source:** The Gazette of Pakistan (Extraordinary), Islamabad, Thursday, August 30, 2001  
**Physical Source Pages:** Pages 23–24 (`data/official_pdfs/fio_2001.pdf`)  
**Stored Content SHA-256:** `69894cf7a3a91bbdcffebdd06e0ee74164a2f8c5c76db3fe2cb3485d11e5dc42`  

---

## 1. EVIDENCE & OFFICIAL PAGE IMAGES

The official Gazette pages have been forensically extracted from `data/official_pdfs/fio_2001.pdf`:
- **Page 23 (Section 22 Sub-sections 1–4):** `data/evidence/fio_s22/fio_p23.png` (Artifact `fio_p23`)
- **Page 24 (Section 22 Sub-sections 4–7 & Section 23):** `data/evidence/fio_s22/fio_p24.png` (Artifact `fio_p24`)
- **Decretal Amount Security Clause Crop:** `data/evidence/fio_s22/fio_s22_amount_crop.png` (Artifact `fio_s22_amount_crop`)

---

## 2. VERBATIM STORED STATUTORY TEXT

```text
22. Appeal. (1) Subject to sub-section (2), any person aggrieved by any judgment, decree, sentence, or final order passed by a Banking Court may, within thirty days of such judgment, decree, sentence or final order prefer an appeal to the High Court.
(2) The appellant shall give notice of the filing of the appeal in accordance with the provisions of Order XLIII Rule 3 of the Code of Civil Procedure (Act V of 1908) to the respondent who may appear before the Banking Court to contest admission of the appeal on the date fixed for hearing.
(3) The High Court shall at the stage of admission of the appeal, or at any time thereafter either suo motu or on the application of the decree holder, decide by means of a reasoned order whether the appeal is to be admitted in part or in whole depending on the facts and circumstances of the case, and as to the security to be furnished by the appellant:
Provided that the admission of the appeal shall not per se operate as a stay, and no shall any stay be granted therein unless the decree-holder has been given an opportunity of being heard and unless the appellant deposits in cash with the High Court an amount equivalent to the decretal amount inclusive of costs, or in the case of an appeal other than an appeal against an interim decree, at the discretion of the High Court furnishes security equal in value to such amount; and in the event of a stay being granted for a part of the decretal amount only, the requirement for a deposit in cash or furnishing of security shall stand reduced accordingly.
(4) An appeal under sub-section (1) shall be heard by a bench of not less that two Judges of the High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of admission.
(5) An appeal may be preferred under this section from a decree passed ex-parte.
(6) No appeal, review or revision shall lie against an order accepting or rejecting an application for leave to defend, or any interlocutory order of the Banking Court which does not dispose of the entire case before the Banking Court other than an order passed under sub-section (11) of section 15 1[or sub-section (13) of section 15A] or sub-section (7) of section 19.
(7) Any order of stay of execution of a decree passed under sub-section (2) shall automatically lapse on the expiry of six months from the date of the order whereupon the amount deposited in Court shall be paid over to the decree-holder or the decree-holder may enforce the security furnished by the judgment-debtor.
```

---

## 3. RAW PDF TEXT LAYER EXTRACTION (PAGES 23–24)

```text
22. Appeal. (1) Subject to sub -section (2), any person aggrieved by any judgment, decree, 
sentence, or final order passed by a Banking Court may, within thi rty days of such judgment, decree, 
sentence or final order prefer an appeal to the High Court. 
(2) The appellant shall give notice of the filing of the appeal in accordance with the provisions 
of Order XLIII Rule 3 of t he Code of Civil Procedure (Act V of 1908) to the respondent who may appear 
before the Banking Court to contest admission of the appeal on the date fixed for hearing. 
(3) The High Court shall at the stage of admission of the appeal, or at any time thereafter either 
suo motu or on the application of the decree holder, decide by means of a reasoned order whether the 
appeal is to be admitted in part or in whole depending on the facts and circumstances of the case, and as 
to the security to be furnished by the appellant: 
Provided that the admission of the appeal shall not per se operate as a stay, and no  shall any 
stay be granted therein unless the decree -holder has been given an opportunity of being heard and 
unless the appellant deposits in cash with the High Court an amount equivalent to the decretal amount 
inclusive of costs, or in the case of an appeal other than an appeal against an interim decree, at the 
discretion of the High Court furnishes security equal in value to such amount; and in the event of a stay 
being granted for a part of the decretal amount only, the requirement for a deposit in cash or furnishing 
of security shall stand reduced accordingly. 
(4) An appeal under sub -section (1) shall be heard by a bench of no t less that two Judges of the 
High Court and, in case the appeal is admitted, it shall be decided within 90 days from the date of 
admission. 
(5) An appeal may be preferred under this section from a decree passed ex -parte. 
(6) No appeal, review or revision shall lie against an order accepting or rejecting an application 
for leave to defend, or any interlocutory order of the Banking Court which does not dispose of the 
entire case before the Banking Court other than an order passed under sub -section (11) of section 15 
1[or sub-section (13) of section 15A] or sub-section (7) of section 19. 
(7) Any order of stay of execution of a decree passed under sub -section (2) shall automatically 
lapse on the expiry of six months from the date of the order whereupon the amount deposited in Court 
shall be paid over to the decree -holder or the decree -holder may enforce the security furnished by the 
judgment -debtor.
```

---

## 4. WORD-LEVEL & CHARACTER-LEVEL DIFF

- **Character Match Ratio:** `0.9978` (99.78%)
- **Word-Level Differences:**
  - `sub -section` vs `sub-section` (hyphen spacing normalized)
  - `thi rty` vs `thirty` (OCR kerning split)
  - `t he` vs `the` (OCR kerning split)
  - `no t` vs `not` (OCR kerning split)
  - **`that` vs `than`** in sub-section (4): Authentic Gazette literally prints `that`.
  - **`no shall` vs `nor shall`** in sub-section (3) proviso: Authentic Gazette literally prints `no shall`.

---

## 5. HUMAN REVIEWER SIGN-OFF TEMPLATE

To promote this provision from `disputed` to `reviewed`, an advocate must physically sign and store the following cryptographically anchored JSON file at `data/reviews/FIO_2001_SEC_22.review.json`:

```json
{
  "canonical_id": "FIO_2001_SEC_22",
  "reviewer_name": "Advocate High Court [Name]",
  "bar_council_id": "P/XXXXX/HC",
  "review_date": "2026-10-27",
  "record_content_hash": "69894cf7a3a91bbdcffebdd06e0ee74164a2f8c5c76db3fe2cb3485d11e5dc42",
  "determination": "approved_verbatim_gazette_with_sic",
  "notes": "Verified against physical Gazette Extraordinary Aug 30, 2001. Typographical errors 'that' and 'no shall' confirmed present in original print. Quoting permitted with [sic] marker.",
  "status": "approved",
  "cryptographic_signature": "SIGNATURE_HASH_HEX"
}
```
*Note: Agents and automated pipelines are strictly forbidden from setting the `reviewed` tier without this signed file.*
