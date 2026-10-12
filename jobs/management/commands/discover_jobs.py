import asyncio
import json
from pathlib import Path
from typing import List, Tuple
import httpx
from django.core.management.base import BaseCommand

from src.config import AppConfig
from src.adapters.greenhouse import GreenhouseAdapter
from src.adapters.jobgether import JobgetherAdapter
from src.adapters.base import BaseJobProvider
from src.orchestrator import DiscoveryOrchestrator
from jobs.services import get_or_create_default_profile, persist_discovery_results
from jobs.models import CandidateProfileModel


class Command(BaseCommand):
    help = "Discovers jobs from Greenhouse and Jobgether, applies daily cap and deduplication, and persists to database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Perform live network discovery against Greenhouse boards and Jobgether API.",
        )
        parser.add_argument(
            "--cap",
            type=int,
            default=100,
            help="Maximum unique jobs cap for this daily discovery run (default: 100).",
        )
        parser.add_argument(
            "--query",
            type=str,
            default="Python",
            help="Keyword query for Jobgether search (default: 'Python').",
        )
        parser.add_argument(
            "--candidate-id",
            type=str,
            default="default-candidate",
            help="Target Candidate Profile ID (default: 'default-candidate').",
        )

    def handle(self, *args, **options):
        is_live = options["live"]
        cap = options["cap"]
        query = options["query"]
        cand_id = options["candidate_id"]

        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE(" ROLEPILOT DISCOVERY PIPELINE EXECUTION"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        # Retrieve or create candidate profile
        candidate_model = CandidateProfileModel.objects.filter(id=cand_id).first()
        if not candidate_model:
            candidate_model = get_or_create_default_profile()

        candidate = candidate_model.to_pydantic()
        self.stdout.write(f"Target Candidate: {candidate.name} ({candidate.home_city or ''}, {candidate.home_country})")
        self.stdout.write(f"Execution Mode: {'LIVE NETWORK' if is_live else 'MOCK SIMULATION'}")
        self.stdout.write(f"Daily Cap: {cap} unique jobs")

        config = AppConfig.load_from_yaml("config/boards.yaml")
        enabled_boards = config.get_enabled_boards()

        providers: List[Tuple[BaseJobProvider, str, str]] = []

        if not is_live:
            # Use deterministic mock fixtures
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
            providers.extend([(gh_adapter, b.token, b.company_name) for b in enabled_boards[:2]])
        else:
            # Live Greenhouse
            gh_adapter = GreenhouseAdapter()
            providers.extend([(gh_adapter, b.token, b.company_name) for b in enabled_boards])

            # Live Jobgether with 100-job daily cap & disk cache
            jobgether_adapter = JobgetherAdapter(enabled=True)
            providers.append((jobgether_adapter, query, "Jobgether Global Search"))

        orchestrator = DiscoveryOrchestrator(per_source_cap=cap)

        # Run async discovery
        jobs, matches, stats = asyncio.run(orchestrator.run_discovery(providers, candidate))

        # Persist into database
        run_record = persist_discovery_results(jobs, matches, stats, candidate_model)

        self.stdout.write(self.style.SUCCESS("\nDISCOVERY COMPLETED & PERSISTED TO DATABASE:"))
        self.stdout.write(f" - Run ID: {run_record.id}")
        self.stdout.write(f" - Status: {run_record.status}")
        self.stdout.write(f" - Unique Jobs Persisted: {run_record.unique_jobs_collected}")
        self.stdout.write(f" - Duplicates Skipped: {run_record.duplicates_skipped}")
        self.stdout.write(f" - Matches Breakdown: {run_record.eligible_count} MATCH | {run_record.review_count} REVIEW | {run_record.ineligible_count} EXCLUDE")
        if run_record.errors:
            self.stdout.write(self.style.WARNING(f" - Notices/Errors: {run_record.errors}"))

        self.stdout.write(self.style.SUCCESS("=" * 70))
