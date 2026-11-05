"""
legal_ai/drafting/template_orchestrator.py

Pakistani Court Pleading Template Orchestrator & Slot Filler.
Combines DigiLawyer's structured template workflow with Section AI's
deep doctrinal verification gates and Article 189/201 precedent bindings.
"""

import io
from typing import Dict, Any, List, Optional
from core.precedent_treatment import check_precedent_treatment, PrecedentStatus
from legal_ai.drafting.chronology_generator import extract_dates_and_events_from_text, format_chronology_markdown
from core.document_builder import generate_court_docx

TEMPLATES_REGISTRY: Dict[str, Dict[str, Any]] = {
    "bail_pre_arrest_498": {
        "id": "bail_pre_arrest_498",
        "title": "Petition for Pre-Arrest Bail under Section 498 CrPC",
        "court_type": "High Court / Court of Session",
        "statute": "Section 498 Code of Criminal Procedure 1898",
        "description": "Protective petition against imminent arrest in non-bailable offences driven by ulterior motives or mala fides.",
        "required_slots": ["court_name", "petitioner", "respondent", "fir_no", "police_station", "offence_sections", "facts"],
        "default_prayer": "It is most respectfully prayed that ad-interim pre-arrest bail may graciously be granted to the Petitioner, and the same be confirmed upon final hearing."
    },
    "bail_post_arrest_497": {
        "id": "bail_post_arrest_497",
        "title": "Petition for Post-Arrest Bail under Section 497 CrPC",
        "court_type": "High Court / Court of Session",
        "statute": "Section 497 Code of Criminal Procedure 1898",
        "description": "Application for release from judicial custody pending trial where case falls under further inquiry or outside prohibitory clause.",
        "required_slots": ["court_name", "petitioner", "respondent", "fir_no", "police_station", "offence_sections", "arrest_date", "facts"],
        "default_prayer": "It is humbly prayed that the Petitioner be admitted to post-arrest bail pending trial, subject to furnishing solvent surety bonds."
    },
    "writ_petition_199": {
        "id": "writ_petition_199",
        "title": "Constitutional Writ Petition under Article 199",
        "court_type": "High Court",
        "statute": "Article 199 of the Constitution of the Islamic Republic of Pakistan 1973",
        "description": "Judicial review against unlawful executive action, jurisdictional excess, or violation of fundamental rights.",
        "required_slots": ["court_name", "petitioner", "respondent", "impugned_order_date", "impugned_authority", "facts"],
        "default_prayer": "It is respectfully prayed that this Hon'ble Court declare the impugned order/action illegal, ultra vires, and void ab initio, and direct the Respondents to act in accordance with law."
    },
    "application_12_2_cpc": {
        "id": "application_12_2_cpc",
        "title": "Application under Section 12(2) CPC (Fraud & Misrepresentation)",
        "court_type": "Civil Court / High Court",
        "statute": "Section 12(2) Code of Civil Procedure 1908",
        "description": "Challenge to decree, judgment, or order obtained through fraud, misrepresentation, or without jurisdiction.",
        "required_slots": ["court_name", "petitioner", "respondent", "suit_no", "decree_date", "fraud_details", "facts"],
        "default_prayer": "It is prayed that the judgment and decree dated **[INSERT DECREE DATE]** be recalled and set aside as fraudulent, null and void."
    },
    "stay_application_o39": {
        "id": "stay_application_o39",
        "title": "Application for Temporary Injunction (Order XXXIX Rules 1 & 2 CPC)",
        "court_type": "Civil Court / High Court",
        "statute": "Order XXXIX Rules 1 and 2 read with Section 151 CPC",
        "description": "Urgent interlocutory application to restrain respondents from alienation, construction, or dispossessing petitioner.",
        "required_slots": ["court_name", "petitioner", "respondent", "suit_title", "property_details", "irreparable_loss_facts"],
        "default_prayer": "It is prayed that an ad-interim injunction be granted restraining the Respondents from alienating or altering the status of the suit property."
    },
    "legal_notice": {
        "id": "legal_notice",
        "title": "Statutory Legal Notice (Section 80 CPC / Contract Breach)",
        "court_type": "Pre-Litigation Demand",
        "statute": "Section 80 CPC / General Contract Law",
        "description": "Formal advocate legal notice serving 60-day demand on Government department or 14-day notice on private party.",
        "required_slots": ["sender_name", "recipient_name", "cause_of_action", "claim_amount", "deadline_days"],
        "default_prayer": "You are hereby called upon to satisfy the aforesaid lawful claim within the statutory period, failing which appropriate legal proceedings shall be initiated."
    }
}

class TemplateOrchestrator:
    """
    Manages Pakistani pleading template rendering, slot binding,
    and verified judicial precedent injection into grounds.
    """

    @staticmethod
    def list_templates() -> List[Dict[str, Any]]:
        return list(TEMPLATES_REGISTRY.values())

    @staticmethod
    def get_template(template_id: str) -> Optional[Dict[str, Any]]:
        return TEMPLATES_REGISTRY.get(template_id)

    @classmethod
    def assemble_pleading_markdown(
        cls,
        template_id: str,
        slots: Dict[str, Any],
        verified_precedents: Optional[List[Dict[str, Any]]] = None,
        include_chronology: bool = True
    ) -> str:
        tpl = cls.get_template(template_id)
        if not tpl:
            raise ValueError(f"Unknown template ID: '{template_id}'")

        court_name = slots.get("court_name") or "THE HONOURABLE HIGH COURT"
        petitioner = slots.get("petitioner") or slots.get("case_title", "**[PETITIONER NAME]**")
        respondent = slots.get("respondent") or "**[RESPONDENTS] and Others**"
        statute = tpl["statute"]
        facts = slots.get("facts") or slots.get("user_facts", "")
        prayer = slots.get("prayer") or tpl["default_prayer"]

        # 1. Caption Block (Pakistani High Court Standard)
        lines = []
        lines.append(f"**IN {court_name.upper()}**\n")
        lines.append(f"**{tpl['title'].upper()}**\n")
        lines.append(f"***{petitioner}***\n... Petitioner / Applicant\n")
        lines.append("*Versus*\n")
        lines.append(f"***{respondent}***\n... Respondents\n")
        lines.append(f"**PETITION UNDER {statute.upper()}**\n")
        lines.append("**RESPECTFULLY SHEWETH:**\n")

        # 2. Chronological List of Dates and Events (Mandatory High Court Annexure)
        if include_chronology and facts:
            events = extract_dates_and_events_from_text(facts)
            lines.append(format_chronology_markdown(events))

        # 3. Facts / Numbered Averments
        lines.append("### BRIEF FACTS:\n")
        fact_paras = [p.strip() for p in facts.split('\n\n') if p.strip()]
        if not fact_paras:
            fact_paras = [
                "1. That the Petitioner is a law-abiding citizen of Pakistan and enjoys all constitutional protections guaranteed under the Constitution.",
                f"2. That the present dispute arose on **[INSERT DATE]** within the territorial jurisdiction of this Hon'ble Court.",
                "3. That the impugned action/order was passed without lawful authority, in gross violation of statutory mandates and principles of natural justice."
            ]
        for i, para in enumerate(fact_paras, 1):
            clean_p = para if para.startswith(f"{i}.") else f"{i}. That {para}"
            lines.append(f"{clean_p}\n")

        # 4. Grounds with Binding Precedents (Article 189/201 Injection)
        lines.append("### GROUNDS:\n")
        ground_idx = ord('A')

        # Inherent jurisdictional ground
        lines.append(f"**{chr(ground_idx)}. Arbitrary and Coram Non Judice:**\n"
                     f"That the impugned action is arbitrary, unreasonable, and void ab initio, having been passed without jurisdiction.\n")
        ground_idx += 1

        # Verified Precedents Injection (5-Part Argument Format)
        if verified_precedents:
            annex_idx = ord('D')
            for prec in verified_precedents:
                cit = prec.get("neutral_citation") or prec.get("case_id") or "Precedent Citation"
                # Shepardizing Check
                treatment = check_precedent_treatment(cit)
                if treatment["status"] == PrecedentStatus.OVERRULED:
                    # Skip overruled precedent to protect advocate from court sanctions
                    continue

                title = prec.get("case_title") or prec.get("title") or "August Court Ruling"
                holding = prec.get("holding_snippet") or prec.get("full_text", "")
                if len(holding) > 300:
                    holding = holding[:300] + "..."

                lines.append(f"**{chr(ground_idx)}. Binding Authority under Article 189/201 of the Constitution:**")
                lines.append(f"In this regard, reliance is emphatically placed upon the landmark dictum of the august Court in ***{title}*** reported as **{cit}**, wherein it was held:")
                lines.append(f"> \"*{holding}*\"\n")
                lines.append(f"(*Copy of the Judgment reported as **{cit}** is attached as **Annexure '{chr(annex_idx)}'***)\n")
                lines.append(f"The ratio decidendi of {cit} squarely applies to the instant matter, rendering the impugned action patently unlawful.\n")
                ground_idx += 1
                annex_idx += 1

        lines.append(f"**{chr(ground_idx)}. General Grounds:**\n"
                     f"That the Petitioner reserves the right to raise further grounds at the time of oral hearing with prior permission of this Hon'ble Court.\n")

        # 5. Prayer Clause
        lines.append("### PRAYER:\n")
        lines.append(f"{prayer}\n")
        lines.append("Any other relief deemed just, equitable, and proper in the circumstances of the case may also graciously be awarded.\n")

        # 6. Advocate Signature & Verification Clause
        lines.append("Through:\n\n**ADVOCATE HIGH COURT / SUPREME COURT**\nCounsel for Petitioner\n\n")
        lines.append("---")
        lines.append("### VERIFICATION:\n")
        lines.append(
            "Verified on oath at **[INSERT PLACE]** this **[INSERT DAY]** day of **[INSERT MONTH, YEAR]** "
            "that the contents of paragraphs 1 to **[N]** of the above petition are true and correct to the best of my knowledge, "
            "and paragraphs **[N+1]** onwards are believed to be true upon information received and legal advice obtained, and nothing has been concealed herein.\n\n"
            "**DEPONENT / PETITIONER**"
        )

        return "\n".join(lines)

    @classmethod
    def generate_docx_stream(
        cls,
        template_id: str,
        slots: Dict[str, Any],
        verified_precedents: Optional[List[Dict[str, Any]]] = None
    ) -> io.BytesIO:
        markdown = cls.assemble_pleading_markdown(template_id, slots, verified_precedents)
        court_name = slots.get("court_name", "High Court of Pakistan")
        case_title = slots.get("case_title") or slots.get("petitioner", "Court Pleading")
        return generate_court_docx(case_title, court_name, markdown)
