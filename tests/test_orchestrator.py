from datetime import datetime, timezone
import pytest

from src.schemas.job import CanonicalJob, WorkMode
from src.schemas.candidate import CandidateProfile
from src.adapters.base import BaseJobProvider, ProviderFetchResult
from src.orchestrator import DiscoveryOrchestrator


def make_dummy_job(job_id: str, title: str, fingerprint: str) -> CanonicalJob:
    now = datetime.now(timezone.utc)
    return CanonicalJob(
        id=f"uuid-{job_id}",
        source="test",
        source_job_id=job_id,
        board_token="test",
        company_name="TestCorp",
        title=title,
        description_raw_html="",
        description_clean_text=f"Description for {title}",
        job_url=f"https://example.com/{job_id}",
        listed_locations=["Remote, India"],
        first_seen_timestamp=now,
        last_seen_timestamp=now,
        last_verified_timestamp=now,
        content_fingerprint=fingerprint,
        work_mode=WorkMode.REMOTE,
        extracted_skills=["Python"],
    )


class MockProvider(BaseJobProvider):
    def __init__(self, name: str, jobs: list, should_fail: bool = False):
        self._name = name
        self.jobs = jobs
        self.should_fail = should_fail

    @property
    def provider_name(self) -> str:
        return self._name

    async def fetch_jobs(self, identifier_or_query: str, **kwargs) -> ProviderFetchResult:
        if self.should_fail:
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=identifier_or_query,
                status="FAILED",
                error_message="Provider connection timeout",
            )
        return ProviderFetchResult(
            provider_name=self.provider_name,
            board_or_query=identifier_or_query,
            jobs=self.jobs,
            total_found=len(self.jobs),
            status="SUCCESS",
        )


@pytest.mark.asyncio
async def test_orchestrator_daily_cap_and_deduplication():
    # 3 jobs, but 2 have identical fingerprints (duplicate content across boards/queries)
    job1 = make_dummy_job("1", "Python Dev 1", "fp_aaa")
    job2 = make_dummy_job("2", "Python Dev 2 (duplicate)", "fp_aaa")
    job3 = make_dummy_job("3", "Python Dev 3", "fp_bbb")
    job4 = make_dummy_job("4", "Python Dev 4", "fp_ccc")

    provider1 = MockProvider("p1", [job1, job2, job3])
    provider2 = MockProvider("p2", [job4])

    candidate = CandidateProfile(home_country="IN", primary_languages=["Python"])
    
    # Set cap at 1 job per source
    orchestrator = DiscoveryOrchestrator(per_source_cap=1)
    jobs, matches, stats = await orchestrator.run_discovery(
        providers_with_queries=[
            (provider1, "query1", "Company1"),
            (provider2, "query2", "Company2"),
        ],
        candidate=candidate,
    )

    # Each provider contributes up to 1 job
    assert len(jobs) == 2
    assert stats.unique_jobs_collected == 2


@pytest.mark.asyncio
async def test_orchestrator_provider_failure_isolation():
    failing_provider = MockProvider("failing", [], should_fail=True)
    working_job = make_dummy_job("10", "Backend Engineer", "fp_10")
    working_provider = MockProvider("working", [working_job])

    candidate = CandidateProfile(home_country="IN", primary_languages=["Python"])
    orchestrator = DiscoveryOrchestrator(per_source_cap=100)

    jobs, matches, stats = await orchestrator.run_discovery(
        providers_with_queries=[
            (failing_provider, "fail_board", "FailCorp"),
            (working_provider, "work_board", "WorkCorp"),
        ],
        candidate=candidate,
    )

    # Failing provider does NOT prevent working provider from succeeding
    assert len(jobs) == 1
    assert stats.provider_results["failing:fail_board"] == "FAILED"
    assert stats.provider_results["working:work_board"] == "SUCCESS"
    assert len(stats.errors) == 1
