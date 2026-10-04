"""Feasibility report generation route."""
from fastapi import APIRouter, HTTPException

from constants.msme import DEFAULT_MSME_ANALYSIS_PROFILE, MSME_CATEGORY_PROFILES
from models.requests import ReportRequest
from services.reporting import (
    build_structured_report,
    generate_narrative_with_fallback,
    render_report_html,
    try_render_pdf_bytes,
)


router = APIRouter()


@router.post("/reports/generate")
def generate_report(payload: ReportRequest):
    try:
        profile = DEFAULT_MSME_ANALYSIS_PROFILE
        if payload.category:
            profile = MSME_CATEGORY_PROFILES.get(payload.category.lower(), DEFAULT_MSME_ANALYSIS_PROFILE)

        structured = build_structured_report(payload.analysis or {}, profile)
        narrative_result = generate_narrative_with_fallback(
            structured,
            business_type=(payload.business_type or payload.category or ''),
            use_llm=bool(payload.use_llm),
            gemini_model=(payload.gemini_model or "gemini-1.5-pro"),
        )
        structured["narrative"] = narrative_result.get("narrative")
        structured["quality_control"] = narrative_result.get("qc")
        structured["generation_meta"] = narrative_result.get("meta")
        html = render_report_html(structured)

        pdf_b64 = None
        if payload.export_pdf:
            pdf_bytes = try_render_pdf_bytes(html)
            if pdf_bytes:
                import base64
                pdf_b64 = base64.b64encode(pdf_bytes).decode('ascii')

        return {
            "status": "success",
            "report": structured,
            "html": html,
            "pdf_base64": pdf_b64,
            "qc": narrative_result.get("qc"),
            "generation_meta": narrative_result.get("meta"),
            "deterministic_backup": narrative_result.get("deterministic_backup"),
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
