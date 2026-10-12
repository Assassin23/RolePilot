import asyncio
import json
import sys
from pathlib import Path
from typing import List, Tuple
import httpx

from src.config import AppConfig
from src.schemas.candidate import CandidateProfile
from src.adapters.greenhouse import GreenhouseAdapter
from src.adapters.jobgether import JobgetherAdapter
from src.adapters.base import BaseJobProvider
from src.orchestrator import DiscoveryOrchestrator


def get_default_candidate() -> CandidateProfile:
    """Default profile for demonstration."""
    return CandidateProfile(
        id="cand-001",
        name="Aditya",
        home_country="IN",
        home_city="Bengaluru",
        target_titles=[
            "Backend Engineer",
            "Python Engineer",
            "Software Engineer",
            "API Engineer"
        ],
        primary_languages=["Python"],
        alternative_languages=["Go", "Java"],
        required_skills=["PostgreSQL", "REST API"],
        preferred_skills=["FastAPI", "Django", "Docker", "Redis", "Kubernetes"],
        excluded_keywords=["Wordpress", "PHP", "Sales", "Data Entry"]
    )


async def run_demo(use_mock_fixtures: bool = True):
    print("=" * 80)
    print(" ROLEPILOT — AUTOMATED JOB DISCOVERY & MATCHING DEMO")
    print("=" * 80)

    candidate = get_default_candidate()
    print(f"\n👤 Active Candidate Profile:")
    print(f"   Name: {candidate.name}")
    print(f"   Home Location: {candidate.home_city or ''}, {candidate.home_country}")
    print(f"   Target Titles: {', '.join(candidate.target_titles[:3])}")
    print(f"   Primary Stack: {', '.join(candidate.primary_languages)} (Alternates: {', '.join(candidate.alternative_languages)})")
    print(f"   Required Skills: {', '.join(candidate.required_skills)}")
    print(f"   Excluded Keywords: {', '.join(candidate.excluded_keywords)}")

    config = AppConfig.load_from_yaml("config/boards.yaml")
    enabled_boards = config.get_enabled_boards()

    orchestrator = DiscoveryOrchestrator(per_source_cap=100)

    providers: List[Tuple[BaseJobProvider, str, str]] = []

    if use_mock_fixtures:
        print("\n🔧 Execution Mode: Safe Local Simulation (Mock Greenhouse & Jobgether APIs)")
        fixture_path = Path("tests/fixtures/greenhouse_mock_jobs.json")
        with open(fixture_path, "r", encoding="utf-8") as f:
            mock_data = json.load(f)

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=mock_data)

        transport = httpx.MockTransport(mock_handler)
        mock_client = httpx.AsyncClient(transport=transport)

        class MockGreenhouseAdapter(GreenhouseAdapter):
            async def fetch_jobs(self, identifier_or_query: str, company_name=None, client=None, **kwargs):
                return await super().fetch_jobs(
                    identifier_or_query=identifier_or_query,
                    company_name=company_name,
                    client=mock_client,
                    **kwargs
                )

        gh_adapter = MockGreenhouseAdapter()
        providers.extend([
            (gh_adapter, b.token, b.company_name) for b in enabled_boards[:2]
        ])
    else:
        print("\n🌐 Execution Mode: Live HTTP Discovery")
        gh_adapter = GreenhouseAdapter()
        providers.extend([
            (gh_adapter, b.token, b.company_name) for b in enabled_boards
        ])

        # Include Jobgether live with 100-job daily cap & caching
        jobgether_adapter = JobgetherAdapter(enabled=True)
        providers.append((jobgether_adapter, "Python", "Jobgether Global Search"))

    # Run discovery & matching
    jobs, matches, stats = await orchestrator.run_discovery(providers, candidate)

    # Display Discovery Statistics
    print("\n" + "-" * 80)
    print("📊 DISCOVERY RUN REPORT & OBSERVABILITY:")
    print(f"   Status: {'SUCCESS' if not stats.errors else 'PARTIAL'}")
    print(f"   Total Fetched (Raw): {stats.total_fetched_raw}")
    print(f"   Unique Normalized Jobs: {stats.unique_jobs_collected}")
    print(f"   Duplicates Skipped: {stats.duplicates_skipped}")
    print(f"   Daily Cap Enforced: {stats.max_job_cap} (Cap reached: {stats.cap_reached})")
    print(f"   Matches: {stats.eligible_count} MATCH | {stats.review_count} REVIEW | {stats.ineligible_count} EXCLUDE")
    print("   Provider Run Statuses:")
    for prov_key, prov_status in stats.provider_results.items():
        print(f"     - {prov_key}: {prov_status}")
    if stats.errors:
        print("   Provider Notices / Errors:")
        for err in stats.errors:
            print(f"     ⚠️ {err}")

    # Display Top Ranked Matches
    print("\n" + "=" * 80)
    print("📋 RANKED CANDIDATE OPPORTUNITIES:")
    print("=" * 80)

    combined = sorted(zip(jobs, matches), key=lambda x: x[1].relevance_score, reverse=True)

    for i, (job, match) in enumerate(combined[:15], 1):
        rec_badge = f"[{match.recommendation.value}]"
        print(f"\n#{i} {rec_badge:10} Score: {match.relevance_score:4.1f}/100 | Work Mode: {job.work_mode.value:7} | Source: {job.source}")
        print(f"   Role: {job.title} @ {job.company_name}")
        print(f"   Locations: {', '.join(job.listed_locations) if job.listed_locations else 'Unspecified'}")
        print(f"   Location Eligibility: {match.eligibility_status.value} ({match.eligibility_reason})")
        print(f"   Skills Extracted: {', '.join(job.extracted_skills)}")
        print(f"   Evaluation: {match.explanation}")
        print(f"   Job URL: {job.job_url}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    is_live = "--live" in sys.argv
    asyncio.run(run_demo(use_mock_fixtures=not is_live))
