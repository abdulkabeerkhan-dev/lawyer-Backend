"""
routers/drafting.py

Modular APIRouter for Pakistani Legal Drafting & Template Orchestration.
Integrates DigiLawyer-style template slot filling with Section AI's
deep doctrinal verification, Shepardizing graph, and High Court compliant .docx generation.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from legal_ai.drafting.template_orchestrator import TemplateOrchestrator, TEMPLATES_REGISTRY
from legal_ai.drafting.chronology_generator import extract_dates_and_events_from_text, format_chronology_markdown
from core.precedent_treatment import check_precedent_treatment
from core.turso_client import get_cases_batch

router = APIRouter(prefix="", tags=["drafting"])

class TemplateFillRequest(BaseModel):
    template_id: str = Field(..., description="ID of the court template (e.g. bail_pre_arrest_498, writ_petition_199)")
    slots: Dict[str, Any] = Field(default_factory=dict, description="Dictionary of slot values (court_name, petitioner, respondent, facts, etc.)")
    selected_case_ids: Optional[List[str]] = Field(default=None, description="Optional list of verified case citations or IDs to bind into grounds")
    export_format: str = Field(default="markdown", description="'markdown' for live canvas or 'docx' for court filing")

class ChronologyRequest(BaseModel):
    facts: str = Field(..., description="Narrative facts or FIR details to extract dates from")
    court_name: Optional[str] = Field(default="High Court", description="Name of the court for heading")

@router.get("/api/v1/drafting/templates")
async def list_drafting_templates():
    """Returns list of pre-built Pakistani court templates with required slots."""
    return {"templates": TemplateOrchestrator.list_templates()}

@router.get("/api/v1/drafting/templates/{template_id}")
async def get_drafting_template_details(template_id: str):
    """Retrieves full specification and required slots for a specific template."""
    tpl = TemplateOrchestrator.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    return {"template": tpl}

@router.post("/api/v1/drafting/generate")
async def generate_drafting_pleading(payload: TemplateFillRequest):
    """
    Fills a court pleading template, binds verified precedents from Turso,
    and returns either formatted Markdown (for split-screen canvas) or a court-ready .docx file.
    """
    tpl = TemplateOrchestrator.get_template(payload.template_id)
    if not tpl:
        raise HTTPException(status_code=400, detail=f"Invalid template_id '{payload.template_id}'.")

    # Fetch verified authorities from Turso if provided
    verified_precedents = []
    if payload.selected_case_ids:
        try:
            verified_precedents = get_cases_batch(payload.selected_case_ids)
        except Exception:
            pass

    # Render Markdown
    markdown = TemplateOrchestrator.assemble_pleading_markdown(
        template_id=payload.template_id,
        slots=payload.slots,
        verified_precedents=verified_precedents
    )

    if payload.export_format.lower() == "docx":
        docx_buffer = TemplateOrchestrator.generate_docx_stream(
            template_id=payload.template_id,
            slots=payload.slots,
            verified_precedents=verified_precedents
        )
        return StreamingResponse(
            docx_buffer,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={payload.template_id}_pleading.docx"}
        )

    return {
        "status": "success",
        "template_id": payload.template_id,
        "title": tpl["title"],
        "markdown": markdown,
        "precedents_bound": len(verified_precedents)
    }

@router.post("/api/v1/drafting/chronology")
async def generate_dates_and_events_chronology(payload: ChronologyRequest):
    """
    Automatically extracts dates and events from narrative text and
    formats as high-court compliant chronological synopsis table.
    """
    events = extract_dates_and_events_from_text(payload.facts)
    markdown_table = format_chronology_markdown(events)
    return {
        "status": "success",
        "events_count": len(events),
        "events": events,
        "markdown_table": markdown_table
    }

@router.get("/api/v1/drafting/check-authority")
async def check_authority_status(citation: str = Query(..., description="Citation to check for negative judicial history")):
    """
    Shepardizing Citator check: verifies whether an authority is Good Law, Overruled, or Distinguished.
    """
    res = check_precedent_treatment(citation)
    return {"result": res}
