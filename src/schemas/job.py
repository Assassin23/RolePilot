import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class WorkMode(str, Enum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    UNKNOWN = "UNKNOWN"


class GeographicScope(str, Enum):
    WORLDWIDE = "WORLDWIDE"
    COUNTRY_SPECIFIC = "COUNTRY_SPECIFIC"
    REGIONAL = "REGIONAL"
    CITY_SPECIFIC = "CITY_SPECIFIC"
    UNKNOWN = "UNKNOWN"


class AnalysisStatus(str, Enum):
    PENDING = "PENDING"
    ANALYZED = "ANALYZED"
    FAILED = "FAILED"


ROLEPILOT_NAMESPACE = uuid.UUID("3d8b2d18-97c8-472d-8622-c38d4e4c2789")


def generate_canonical_job_id(source: str, board_token: str, source_job_id: str) -> str:
    """Generates a reproducible, deterministic UUID for a job post."""
    key = f"{source.strip().lower()}:{board_token.strip().lower()}:{source_job_id.strip()}"
    return str(uuid.uuid5(ROLEPILOT_NAMESPACE, key))


class CanonicalJob(BaseModel):
    id: str = Field(description="Deterministic UUID derived from source, board_token, and source_job_id")
    source: str = Field(default="greenhouse")
    source_job_id: str
    board_token: str
    company_name: str
    title: str
    description_raw_html: str
    description_clean_text: str
    job_url: str
    application_url: Optional[str] = None
    listed_locations: List[str] = Field(default_factory=list)
    departments: List[str] = Field(default_factory=list)
    offices: List[str] = Field(default_factory=list)
    publication_timestamp: Optional[datetime] = None
    source_update_timestamp: Optional[datetime] = None
    first_seen_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_verified_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_fingerprint: str = Field(description="SHA-256 hash of normalized text")
    is_active: bool = True

    # Analysis Results
    work_mode: WorkMode = WorkMode.UNKNOWN
    work_mode_evidence: Optional[str] = None
    geographic_scope: GeographicScope = GeographicScope.UNKNOWN
    allowed_countries: List[str] = Field(default_factory=list, description="ISO-3166-1 alpha-2 codes")
    excluded_countries: List[str] = Field(default_factory=list)
    allowed_cities: List[str] = Field(default_factory=list)
    extracted_skills: List[str] = Field(default_factory=list)
    seniority_level: str = "UNKNOWN"
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING

    model_config = {
        "extra": "ignore",
    }


class GreenhouseJobRaw(BaseModel):
    """Pydantic model representing raw items received directly from Greenhouse API."""
    id: int | str
    title: str
    updated_at: Optional[str] = None
    first_published: Optional[str] = None
    requisition_id: Optional[str] = None
    absolute_url: Optional[str] = None
    location: Optional[dict] = None
    departments: Optional[List[dict]] = None
    offices: Optional[List[dict]] = None
    content: Optional[str] = None

    model_config = {"extra": "allow"}
