"""Pydantic request bodies for every API route."""
from datetime import date

from pydantic import BaseModel


class RegisterUser(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    street: str | None = None
    barangay: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    birthday: date | None = None
    primary_business: str | None = None
    preferred_setup: str | None = None
    privacy_consent: bool = False
    privacy_policy_version: str | None = None


class LoginUser(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class UpdateUserProfile(BaseModel):
    full_name: str
    email: str
    address: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    birthday: date | None = None
    primary_business: str | None = None
    preferred_setup: str | None = None
    # Left out (None) keeps what's saved, so a form that doesn't show these
    # fields can't erase them. An empty string clears the address parts.
    first_name: str | None = None
    last_name: str | None = None
    street: str | None = None
    barangay: str | None = None


class AnalysisRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340
    user_id: int | None = None
    history_id: int | None = None


class CompetitorPreviewRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminCreateMsme(BaseModel):
    name: str
    business_type: str
    latitude: float
    longitude: float


class AdminUpdateMsme(AdminCreateMsme):
    pass


class AdminVerifiedLocalFeatureRequest(BaseModel):
    feature_kind: str
    name: str
    latitude: float
    longitude: float
    business_type: str | None = None
    feature_subtype: str | None = None
    road_class: str | None = None
    power: int | None = None
    building_type: str | None = None
    landuse: str | None = None
    area_m2: float | None = None
    confidence_score: int = 100
    source_note: str | None = None
    verified_at: date | None = None
    is_active: bool = True


class AdminUpdateUser(BaseModel):
    full_name: str
    email: str
    address: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    birthday: date | None = None
    primary_business: str | None = None
    preferred_setup: str | None = None


class UserSpaceSubmissionRequest(BaseModel):
    user_id: int
    title: str
    listing_mode: str
    property_type: str | None = None
    business_type: str | None = None
    latitude: float
    longitude: float
    address_text: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    contact_info: str | None = None
    notes: str | None = None
    photo_urls: list[str] | None = None


class AdminSpaceSubmissionRequest(BaseModel):
    title: str
    listing_mode: str
    guarantee_level: str = "potential"
    confidence_score: int | None = None
    property_type: str | None = None
    business_type: str | None = None
    latitude: float
    longitude: float
    address_text: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    source_note: str | None = None
    contact_info: str | None = None
    notes: str | None = None
    photo_urls: list[str] | None = None
    verified_at: date | None = None
    expires_at: date | None = None
    is_active: bool = True


class AdminToggleSpaceSubmissionActiveRequest(BaseModel):
    is_active: bool


class AdminReviewUserSpaceSubmissionRequest(BaseModel):
    status: str
    review_note: str | None = None


class ReportRequest(BaseModel):
    analysis: dict | None = None
    # The full POST /analyze result. When present, the narrative is built from it
    # instead of re-scoring the thinner `analysis` payload.
    scan: dict | None = None
    category: str | None = None
    export_pdf: bool = False
    business_type: str | None = None
    use_llm: bool = True
    # None uses services.reporting.DEFAULT_GEMINI_MODEL (the GEMINI_MODEL env var).
    gemini_model: str | None = None


class AdminMapLayerCreateRequest(BaseModel):
    category: str
    name: str
    source_note: str | None = None
    geojson: dict
    activate: bool = False


class AdminMapLayerUpdateRequest(BaseModel):
    name: str
    source_note: str | None = None
    geojson: dict


class AdminZoningAllowedUsesRequest(BaseModel):
    # zone_class -> business types allowed there
    allowed: dict[str, list[str]]
