"""Health-check routes."""
from fastapi import APIRouter


router = APIRouter()


@router.get("/")
def root():
    return {
        "status": "success",
        "service": "MarketScope API"
    }


@router.head("/")
def root_head():
    return
