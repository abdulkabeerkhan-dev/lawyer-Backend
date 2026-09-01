# Legal Petition Drafting Format (Pakistan — Constitutional Writ Style)

This template captures the **structure, tone, and formatting conventions** used in this firm's writ petitions, so an AI drafting assistant can reproduce the same style for any new matter. Replace all `[bracketed]` placeholders with case-specific content.

---

## 1. Caption Block

```
**IN THE HONOURABLE [COURT NAME] HIGH COURT**

**WRIT PETITION NO. ____________ / [YEAR]**

***[Petitioner Full Name/Title]***
                                                                ... Petitioner

*Versus*

	***[Respondent 1 Name] and Others***
                                                                … Respondents

**PETITION UNDER ARTICLE [X] OF THE CONSTITUTION OF THE ISLAMIC REPUBLIC OF PAKISTAN 1973 READ WITH ALL OTHER ENABLING PROVISIONS OF LAW**

**SUBMISSIONS ON BEHALF OF THE [PETITIONER/RESPONDENT]**
```

**Formatting rules:**
- Court name: bold, all caps, centered conceptually (left-aligned in practice).
- Petition number: bold, blank underscore for filing-stamp number, year in bold.
- Party names: italicized; titles (Dr., etc.) included where relevant.
- "… Petitioner" / "… Respondents" right-aligned (or tab-indented), preceded by ellipsis, not a period.
- "Versus" italicized, standalone line, centered.
- Statutory basis heading: bold, all caps.
- Section heading ("SUBMISSIONS ON BEHALF OF…"): bold, all caps.

---

## 2. Argument / Submission Structure

Each ground of argument follows this **repeating five-part pattern**:

1. **Bolded thesis statement** — a single bolded paragraph (bullet) stating the core legal proposition for that ground, in strong/assertive language (e.g., "patently unlawful, illegal and unjustifiable").
2. **Introductory sentence placing reliance on authority** — plain text, e.g., *"In this regard, reliance is firstly placed upon the commentary rendered by this Hon'ble Court in judgment reported as **[Citation]**, wherein it was unequivocally/categorically/emphatically held:"*
3. **Block quotation of the judgment** — italicized, paragraph-numbered (bold paragraph numbers e.g. `***7.***`), reproducing the court's exact language. Key phrases within the quote are bolded for emphasis. Ellipses (`…`) used to skip non-essential text.
4. **Annexure citation line** — italicized, parenthetical, immediately after the quote:
   `(*Copy of the Judgment reported as **[Citation]** is attached as **Annexure [Letter]***)`
5. **Application paragraph** — plain text connecting the quoted precedent back to the facts of the instant case, ending in a concluding submission (e.g., "...rendering the Petitioner lawfully entitled to...").

This 5-part cycle **repeats for each authority cited**, building a cumulative chain of precedent before arriving at the final submission/prayer for that ground.

### Template for one argument block:

```markdown
- **[Bolded thesis statement of the legal proposition for this ground.]**

- In this regard, reliance is [firstly/further/similarly] placed upon the judgment
  [of this Hon'ble Court / of the Supreme Court / reported as] **[Citation]**,
  wherein it was [unequivocally/categorically/emphatically] held:

"*[Para No.]. [Verbatim or paraphrased quoted text from the judgment, with
**key phrases bolded** for emphasis]*"

(*Copy of [the] Judgment reported as **[Citation]** is attached as
**Annexure [Letter]***)

[Application paragraph: tie the precedent to the facts of the present case.
End with a clear submission, e.g., "Therefore, the Petitioner is entitled to..."]
```

---

## 3. Citation Conventions

- **Case law citation format:** `[Year] [Reporter] [Volume/Court abbreviation] [Page]`
  Examples: `2020 Islamabad 454`, `PLD 2016 SC 570`, `2015 SCMR 630`, `2017 PCrLJ 1569`, `PLD 2014 Sindh 389`.
- **Statute citation:** full name + year, section number spelled out (e.g., "section 24A of the General Clauses Act 1897").
- **Defined terms:** introduced once in quotation marks with bold, followed by the abbreviation in parentheses and quotes, e.g., `Exit Control List ("ECL")`, `Passport Control List ("PCL")`.
- **Annexures:** lettered sequentially (A, B, C…) in order of first reference; each annexure reference is italicized and parenthetical, sometimes noting page ranges, e.g., `[pg. 21-42]`.
- **Latin/legal terms** (e.g., *mala fide*, *vide*) are italicized.
- **Emphasis within quotes:** bolding is used liberally inside block quotations to highlight the operative legal principle the drafter wants the reader to focus on; a closing note `(emphasis added)` follows when this is done deliberately.

---

## 4. Tone & Language Patterns

- Formal, traditional Pakistani legal drafting register — avoid contractions, use "it is submitted," "it is respectfully submitted," "in light thereof," "thus," "whereas."
- Each ground ends with a **conclusory sentence** restating the relief sought as a logical consequence of the precedent ("…rendering the Petitioner lawfully entitled to have her name expunged from the ECL.").
- Transitions between grounds use formal connectors: "Moreover," "Furthermore," "Similarly," "Much in a similar vein," "In this respect."
- Numbers/sections referenced inline without over-explaining (assumes a legally literate reader, i.e., the court/opposing counsel).
- Avoid first person; always third person ("the Petitioner," "this Hon'ble Court," "the Respondents").

---

## 5. Reusable Section Skeleton (for any petition)

```markdown
**IN THE HONOURABLE [COURT] HIGH COURT**
**WRIT PETITION NO. ____________ / [YEAR]**
***[Petitioner]***                                            ... Petitioner
*Versus*
***[Respondent] and Others***                                 … Respondents

**PETITION UNDER ARTICLE [X] OF THE CONSTITUTION...**
**SUBMISSIONS ON BEHALF OF THE [PARTY]**

- **[Ground 1 thesis statement]**
  [precedent block(s) per the 5-part pattern above]
  [application paragraph]

- **[Ground 2 thesis statement]**
  [precedent block(s)]
  [application paragraph]

  ... repeat for each ground ...

[Concluding prayer / relief sought paragraph]
```

---

## 6. Usage Notes for AI Drafting

When generating a new document in this format:
1. Always start with the full caption block, adapting court, petition type, and party names.
2. State the constitutional/statutory basis for the petition immediately after the caption.
3. Build each argument as: **bold thesis → cited authority → block quote → annexure note → application to facts**.
4. Maintain sequential, alphabetical annexure lettering across the whole document.
5. Keep verbatim quotations faithful to source judgments — do not paraphrase quoted judicial text; only paraphrase the surrounding analysis.
6. Close each ground with an explicit conclusion connecting precedent to relief sought.
7. Maintain bold/italic formatting conventions exactly as outlined above for consistency with firm style.

---

*This file is a structural/style template only. It does not reproduce the confidential case-specific content of the original source document.*