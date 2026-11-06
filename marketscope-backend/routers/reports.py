"""Feasibility report generation route."""
from fastapi import APIRouter, HTTPException

from constants.msme import DEFAULT_MSME_ANALYSIS_PROFILE, MSME_CATEGORY_PROFILES
from models.requests import ReportRequest
from services.reporting import (
    DEFAULT_GEMINI_MODEL,
    build_structured_report,
    generate_narrative_from_scan,
    generate_narrative_with_fallback,
    render_report_html,
    try_render_pdf_bytes,
)


router = APIRouter()


@router.post("/reports/generate")
def generate_report(payload: ReportRequest):
    try:
        gemini_model = payload.gemini_model or DEFAULT_GEMINI_MODEL
        business_type = payload.business_type or payload.category or ''

        if payload.scan:
            # Narrative from the real scan result, so it quotes the same scores the user sees.
            narrative_result = generate_narrative_from_scan(
                payload.scan,
                business_type=business_type,
                use_llm=bool(payload.use_llm),
                gemini_model=gemini_model,
            )
            return {
                "status": "success",
                "report": {
                    "narrative": narrative_result.get("narrative"),
                    "quality_control": narrative_result.get("qc"),
                    "generation_meta": narrative_result.get("meta"),
                },
                "html": None,
                "pdf_base64": None,
                "qc": narrative_result.get("qc"),
                "generation_meta": narrative_result.get("meta"),
                "deterministic_backup": narrative_result.get("deterministic_backup"),
            }

        profile = DEFAULT_MSME_ANALYSIS_PROFILE
        if payload.category:
            profile = MSME_CATEGORY_PROFILES.get(payload.category.lower(), DEFAULT_MSME_ANALYSIS_PROFILE)

        structured = build_structured_report(payload.analysis or {}, profile)
        narrative_result = generate_narrative_with_fallback(
            structured,
            business_type=business_type,
            use_llm=bool(payload.use_llm),
            gemini_model=gemini_model,
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
