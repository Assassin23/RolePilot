from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class Recommendation(str, Enum):
    MATCH = "MATCH"
    REVIEW = "REVIEW"
    EXCLUDE = "EXCLUDE"


class CandidateProfile(BaseModel):
    id: str = "candidate-1"
    name: str = "Candidate"
    home_country: str = Field(..., description="ISO 3166-1 alpha-2 country code, e.g. 'IN'")
    home_city: Optional[str] = Field(None, description="Home city, e.g. 'Bengaluru' or 'Dehradun'")
    target_titles: List[str] = Field(
        default_factory=lambda: [
            "Backend Engineer",
            "Python Developer",
            "Software Engineer",
            "API Engineer",
            "Django Developer",
            "FastAPI Developer"
        ]
    )
    primary_languages: List[str] = Field(
        default_factory=lambda: ["Python"],
        description="Core programming languages sought (not human spoken languages)"
    )
    alternative_languages: List[str] = Field(
        default_factory=lambda: ["Go", "Java"],
        description="Acceptable alternate programming languages"
    )
    required_skills: List[str] = Field(
        default_factory=lambda: ["PostgreSQL", "REST API"]
    )
    preferred_skills: List[str] = Field(
        default_factory=lambda: ["Docker", "Redis", "FastAPI", "Django", "CI/CD", "Kubernetes"]
    )
    excluded_keywords: List[str] = Field(
        default_factory=lambda: ["Wordpress", "PHP", "Sales", "Data Entry", "Ruby on Rails"]
    )
    min_seniority: Optional[str] = None


class CandidateMatchResult(BaseModel):
    candidate_id: str
    job_id: str
    relevance_score: float = Field(ge=0.0, le=100.0)
    recommendation: Recommendation
    eligibility_status: EligibilityStatus
    eligibility_reason: str
    matched_titles: List[str] = Field(default_factory=list)
    matched_languages: List[str] = Field(default_factory=list)
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    exclusion_reasons: List[str] = Field(default_factory=list)
    explanation: str = ""
