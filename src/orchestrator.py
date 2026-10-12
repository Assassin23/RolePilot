import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel, Field

from src.schemas.job import CanonicalJob
from src.schemas.candidate import CandidateProfile, CandidateMatchResult
from src.adapters.base import BaseJobProvider
from src.matcher.relevance import evaluate_candidate_match

logger = logging.getLogger(__name__)


class DiscoveryRunStats(BaseModel):
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    per_source_cap: int = 100
    max_job_cap: int = 100
    total_fetched_raw: int = 0
    unique_jobs_collected: int = 0
    duplicates_skipped: int = 0
    cap_reached: bool = False
    eligible_count: int = 0
    review_count: int = 0
    ineligible_count: int = 0
    provider_results: Dict[str, str] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class DiscoveryOrchestrator:
    """
    Orchestrates job discovery across configured providers.
    - Rate rules: Jobgether capped at 100 jobs daily; company boards fetch up to 100 jobs each.
    - Enforces global deduplication by content fingerprint and unique source ID.
    - Evaluates candidate relevance and location eligibility for each unique posting.
    """

    def __init__(self, per_source_cap: int = 100, max_daily_cap: Optional[int] = None):
        if max_daily_cap is not None:
            self.per_source_cap = max_daily_cap
        else:
            self.per_source_cap = per_source_cap

    async def run_discovery(
        self,
        providers_with_queries: List[Tuple[BaseJobProvider, str, Optional[str]]],
        candidate: CandidateProfile,
        existing_fingerprints: Optional[set] = None,
    ) -> Tuple[List[CanonicalJob], List[CandidateMatchResult], DiscoveryRunStats]:
        """
        Runs discovery across all providers.
        providers_with_queries: List of (provider_instance, query_or_token, optional_company_name)
        """
        stats = DiscoveryRunStats(per_source_cap=self.per_source_cap, max_job_cap=self.per_source_cap)
        seen_fingerprints = set(existing_fingerprints or [])
        seen_ids = set()

        collected_jobs: List[CanonicalJob] = []
        match_results: List[CandidateMatchResult] = []

        for provider, identifier, company_name in providers_with_queries:
            provider_key = f"{provider.provider_name}:{identifier}"
            source_jobs_collected = 0

            try:
                result = await provider.fetch_jobs(
                    identifier_or_query=identifier,
                    company_name=company_name
                )
                stats.provider_results[provider_key] = result.status
                if result.status != "SUCCESS":
                    if result.error_message:
                        stats.errors.append(f"[{provider_key}] {result.error_message}")
                    continue

                stats.total_fetched_raw += result.total_found

                for job in result.jobs:
                    # Enforce per-source quota (e.g. max 100 jobs per company board)
                    if source_jobs_collected >= self.per_source_cap:
                        break

                    # Deduplication by ID and Content Fingerprint
                    if job.id in seen_ids or job.content_fingerprint in seen_fingerprints:
                        stats.duplicates_skipped += 1
                        continue

                    source_jobs_collected += 1
                    seen_ids.add(job.id)
                    seen_fingerprints.add(job.content_fingerprint)
                    collected_jobs.append(job)

                    # Evaluate candidate match
                    match = evaluate_candidate_match(job, candidate)
                    match_results.append(match)

                    if match.recommendation.value == "MATCH":
                        stats.eligible_count += 1
                    elif match.recommendation.value == "REVIEW":
                        stats.review_count += 1
                    else:
                        stats.ineligible_count += 1

            except Exception as e:
                err_msg = f"Unexpected failure in provider {provider_key}: {str(e)}"
                logger.exception(err_msg)
                stats.provider_results[provider_key] = "FAILED"
                stats.errors.append(err_msg)

        stats.unique_jobs_collected = len(collected_jobs)
        stats.completed_at = datetime.now(timezone.utc)
        return collected_jobs, match_results, stats
