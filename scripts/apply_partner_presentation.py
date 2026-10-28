import os
import re

repo_dir = r"I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
main_path = os.path.join(repo_dir, "main.py")

with open(main_path, "r", encoding="utf-8") as f:
    content = f.read()

target_start = "        if is_precedent_blocked:"
target_end = "        return {"

start_idx = content.find(target_start)
end_idx = content.find(target_end, start_idx)

if start_idx == -1 or end_idx == -1:
    raise ValueError(f"Could not find slice in main.py: start_idx={start_idx}, end_idx={end_idx}")

new_block = '''        notice_text = ""
        if is_precedent_blocked:
            cit_list_str = ", ".join(f"**`{c}`**" for c in unverified_cits) if unverified_cits else "the requested judicial citation or authority"
            notice_text = (
                f"> **Precedent Verification Notice**: The requested authority {cit_list_str} "
                f"could not be verified in authoritative Pakistani law reports (*SCMR*, *PLD*, *YLR*, *CLC*, *PCrLJ*, *MLD*, *CLD*, *PTD*, *PLC*) "
                f"or the verified precedent index.\\n\\n"
            )
            # ORDER 2.1 - ITEM 3: Authenticity Notice only when pagination check failed
            if pagination_check_failed:
                notice_text += (
                    f"> **Authenticity Notice**: In Pakistani law reporting, annual journal volumes typically contain under 2,000–2,500 pages. "
                    f"Citations with out-of-range pagination or unindexed case names do not correspond to authentic superior court judgments. "
                    f"To protect strict judicial accuracy and prevent synthetic AI hallucinations, Section strictly withholds analysis for unverified authorities.\\n\\n"
                )
        elif err_cat == "STATUTORY_MISQUOTATION":
            notice_text = (
                f"> **Statutory Verification Notice**: Direct narrative analysis was withheld to protect strict statutory accuracy. "
                f"The generated draft contained statutory quotations that differed from authentic gazette prints. "
                f"The authentic, verbatim text of controlling statutory provisions from official gazettes is set out below for legal reliance.\\n\\n"
            )
        elif err_cat == "UNSOURCED_ANALYSIS":
            notice_text = (
                f"> **Analysis Verification Notice**: Direct narrative analysis was withheld because the proposed draft contained "
                f"propositions that were not directly anchored in authenticated statutory gazettes or indexed judicial holdings. "
                f"The verified controlling legal authorities on record are set out below.\\n\\n"
            )
        else:
            notice_lead = "The authentic, verbatim text of the controlling statutory provisions from official gazettes is set out below for legal reliance.\\n\\n" if verified_texts else "Analysis was withheld to protect strict legal accuracy.\\n\\n"
            notice_text = f"> **Verification Notice**: Direct narrative analysis was withheld to protect strict statutory accuracy. {notice_lead}"

        response_text = ""

        # ORDER 2.1 - ITEM 5: Verified provisions go under Verified Statutory Provisions on Record
        if verified_texts:
            clean_vtexts = [re.sub(r'^#\\s+', '', vt) for vt in verified_texts]
            response_text += "### Verified Statutory Provisions on Record\\n\\n" + "\\n\\n---\\n\\n".join(clean_vtexts) + "\\n\\n"

        # ORDER 2.1 - ITEM 5: Missing Acts or provisions with no stored text go under \"Not in verified store\"
        if missing_provisions:
            response_text += "### Not in verified store\\n\\n"
            for mp in missing_provisions:
                response_text += f"- **{mp}**: no text available\\n"
            response_text += "\\n"

        # ORDER 2.1 - ITEM 7: Label \"Retrieved by keyword match, relevance not assessed\" (never \"Verified Judicial Authorities\")
        if precedent_cards:
            response_text += "### Retrieved by keyword match, relevance not assessed\\n\\n"
            for pc in precedent_cards[:5]:
                cit = pc.get("citation") or pc.get("title") or "Judicial Precedent"
                case_t = pc.get("case_title") or pc.get("title") or ""
                court = pc.get("court") or "Superior Court"
                holding = pc.get("holding") or pc.get("summary") or pc.get("snippet") or ""

                # ORDER 2.1 - ITEM 10: Strip CITATION:... TITLE:... blobs and truncate at word boundary
                holding_clean = re.sub(r'^(?:\[[^\]]*\]\s*)?(?:CITATION:\s*[^\\n]+\s*)?(?:TITLE:\s*[^\\n]+\s*)?(?:COURT:\s*[^\\n]+\s*)?(?:BENCH:\s*[^\\n]+\s*)?', '', holding.strip(), flags=re.IGNORECASE).strip()
                if len(holding_clean) > 250:
                    holding_clean = holding_clean[:250].rsplit(' ', 1)[0] + '...'

                response_text += f"- **{cit}** — *{case_t}* ({court})\\n"
                if holding_clean:
                    response_text += f"  > {holding_clean}\\n\\n"

        # Substantive notice disclosures placed at the bottom so no warnings are shown at the top
        if notice_text:
            response_text += f"---\\n\\n{notice_text.strip()}\\n\\n"

        # ORDER 2.1 - ITEM 3: Legal Guidance only when pagination check failed
        if pagination_check_failed and job.get("retry_guidance"):
            response_text += f"> **Legal Guidance**: {job['retry_guidance']}\\n\\n"

        from legal_ai.synthesis.memorandum_generator import sanitize_partner_markdown_presentation
        response_text = sanitize_partner_markdown_presentation(response_text)
\n'''

content = content[:start_idx] + new_block + content[end_idx:]

with open(main_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully applied partner presentation update to main.py!")
