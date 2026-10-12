from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class ATSProvider(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    UNKNOWN = "unknown"


class InspectionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNSUPPORTED_ATS = "UNSUPPORTED_ATS"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"


class InspectionRequest(BaseModel):
    company_name: str = Field(..., description="Name of the company, e.g. 'Cloudflare'")
    careers_url: str = Field(..., description="Official careers page URL, e.g. 'https://www.cloudflare.com/careers/'")
    slug_hint: Optional[str] = Field(None, description="Optional ATS slug hint, e.g. 'cloudflare'")


class InspectionResponse(BaseModel):
    status: InspectionStatus
    company_name: str
    careers_url: str
    detected_ats: ATSProvider
    board_identifier: Optional[str] = None
    api_endpoint: Optional[str] = None
    is_api_accessible: bool = False
    published_jobs_count: int = 0
    confidence: str = "NONE"  # "HIGH", "MEDIUM", "LOW", "NONE"
    evidence: str = ""
    inspected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BatchCatalogRequest(BaseModel):
    limit: Optional[int] = Field(None, description="Max companies from catalog to inspect (default all 100)")
    concurrency: int = Field(5, description="Concurrent workers (default 5, max 10)")


class BatchCatalogResponse(BaseModel):
    total_inspected: int
    verified_greenhouse_count: int
    unsupported_ats_count: int
    not_found_count: int
    error_count: int
    verified_greenhouse_boards: list[dict]
    results: list[InspectionResponse]

