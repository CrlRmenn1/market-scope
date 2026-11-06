"""Site analysis and competitor preview routes."""
from fastapi import APIRouter, Depends

from core.auth import require_user
from core.rate_limit import check_rate_limit
from models.requests import AnalysisRequest, CompetitorPreviewRequest
from services.analysis import perform_analysis
from services.scoring import collect_competitor_preview


router = APIRouter()


# The analysis itself lives in services/analysis.py because the citywide
# trend scan (services/trend_scan.py) calls it directly too.
@router.post("/analyze")
def analyze(data: AnalysisRequest, current_user_id: int = Depends(require_user)):
    check_rate_limit(f"analyze:user:{current_user_id}", 120, 60 * 60, "Too many scans. Try again in a little while.")
    # A scan is saved to the caller's own history, whatever id the request names.
    # No id means an unsaved scan, such as the tour.
    owner_id = current_user_id if data.user_id is not None else None
    return perform_analysis(data.model_copy(update={"user_id": owner_id}))


@router.post("/competitors/preview", dependencies=[Depends(require_user)])
def preview_competitors(data: CompetitorPreviewRequest):
    preview = collect_competitor_preview(data.lat, data.lon, data.radius, data.business_type)
    return {
        "status": "success",
        **preview,
    }
