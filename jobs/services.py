import logging
from typing import List, Tuple
from django.db import transaction

from src.schemas.job import CanonicalJob
from src.schemas.candidate import CandidateMatchResult
from src.orchestrator import DiscoveryRunStats
from jobs.models import (
    CanonicalJobModel,
    DiscoveryRunModel,
    CandidateProfileModel,
    CandidateJobMatchModel,
)

logger = logging.getLogger(__name__)


def get_or_create_default_profile() -> CandidateProfileModel:
    """Ensures at least one active Candidate Profile exists."""
    profile, _ = CandidateProfileModel.objects.get_or_create(
        id="default-candidate",
        defaults={
            "name": "Aditya",
            "home_country": "IN",
            "home_city": "Bengaluru",
            "target_titles": [
                "Backend Engineer",
                "Python Engineer",
                "Software Engineer",
                "API Engineer"
            ],
            "primary_languages": ["Python"],
            "alternative_languages": ["Go", "Java"],
            "required_skills": ["PostgreSQL", "REST API"],
            "preferred_skills": ["FastAPI", "Django", "Docker", "Redis", "Kubernetes"],
            "excluded_keywords": ["Wordpress", "PHP", "Sales", "Data Entry"],
        }
    )
    return profile


@transaction.atomic
def persist_discovery_results(
    jobs: List[CanonicalJob],
    matches: List[CandidateMatchResult],
    stats: DiscoveryRunStats,
    candidate_profile_model: CandidateProfileModel,
) -> DiscoveryRunModel:
    """
    Persists discovered canonical jobs, discovery run telemetry, and candidate matches.
    Idempotent: updates existing jobs and matches rather than duplicating.
    """
    # 1. Persist Canonical Jobs
    job_model_map = {}
    for job in jobs:
        obj, _ = CanonicalJobModel.objects.update_or_create(
            id=job.id,
            defaults={
                "source": job.source,
                "source_job_id": job.source_job_id,
                "board_token": job.board_token,
                "company_name": job.company_name,
                "title": job.title,
                "description_raw_html": job.description_raw_html,
                "description_clean_text": job.description_clean_text,
                "job_url": str(job.job_url),
                "application_url": str(job.application_url) if job.application_url else None,
                "listed_locations": job.listed_locations,
                "departments": job.departments,
                "offices": job.offices,
                "publication_timestamp": job.publication_timestamp,
                "source_update_timestamp": job.source_update_timestamp,
                "content_fingerprint": job.content_fingerprint,
                "is_active": job.is_active,
                "work_mode": job.work_mode.value,
                "work_mode_evidence": job.work_mode_evidence,
                "geographic_scope": job.geographic_scope.value,
                "extracted_skills": job.extracted_skills,
                "seniority_level": job.seniority_level,
                "analysis_status": job.analysis_status.value,
            }
        )
        job_model_map[job.id] = obj

    # 2. Persist Matches
    for match in matches:
        job_obj = job_model_map.get(match.job_id) or CanonicalJobModel.objects.filter(id=match.job_id).first()
        if not job_obj:
            continue
        match_id = f"{candidate_profile_model.id}:{match.job_id}"
        CandidateJobMatchModel.objects.update_or_create(
            id=match_id,
            defaults={
                "candidate": candidate_profile_model,
                "job": job_obj,
                "relevance_score": match.relevance_score,
                "recommendation": match.recommendation.value,
                "eligibility_status": match.eligibility_status.value,
                "eligibility_reason": match.eligibility_reason,
                "matched_titles": match.matched_titles,
                "matched_languages": match.matched_languages,
                "matched_skills": match.matched_skills,
                "missing_skills": match.missing_skills,
                "exclusion_reasons": match.exclusion_reasons,
                "explanation": match.explanation,
            }
        )

    # 3. Record Discovery Run
    run_status = "SUCCESS" if not stats.errors else ("PARTIAL" if stats.unique_jobs_collected > 0 else "FAILED")
    run_record = DiscoveryRunModel.objects.create(
        completed_at=stats.completed_at,
        max_job_cap=getattr(stats, "max_job_cap", getattr(stats, "per_source_cap", 100)),
        total_fetched_raw=stats.total_fetched_raw,
        unique_jobs_collected=stats.unique_jobs_collected,
        duplicates_skipped=stats.duplicates_skipped,
        cap_reached=stats.cap_reached,
        eligible_count=stats.eligible_count,
        review_count=stats.review_count,
        ineligible_count=stats.ineligible_count,
        provider_results=stats.provider_results,
        errors=stats.errors,
        status=run_status,
    )

    return run_record
