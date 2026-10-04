"""Site analysis and competitor preview routes."""
from fastapi import APIRouter

from models.requests import CompetitorPreviewRequest
from services.analysis import perform_analysis
from services.scoring import collect_competitor_preview


router = APIRouter()


# The analysis itself lives in services/analysis.py because the citywide
# trend scan (services/trend_scan.py) calls it directly too.
router.add_api_route("/analyze", perform_analysis, methods=["POST"])


@router.post("/competitors/preview")
def preview_competitors(data: CompetitorPreviewRequest):
    preview = collect_competitor_preview(data.lat, data.lon, data.radius, data.business_type)
    return {
        "status": "success",
        **preview,
    }
