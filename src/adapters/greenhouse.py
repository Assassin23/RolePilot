import logging
from datetime import datetime, timezone
from typing import List, Optional
import httpx

from src.schemas.job import CanonicalJob, generate_canonical_job_id
from src.analyzer.pipeline import analyze_job
from src.adapters.base import BaseJobProvider, ProviderFetchResult

logger = logging.getLogger(__name__)


class GreenhouseAdapter(BaseJobProvider):
    """
    Adapter for Greenhouse Job Board API.
    Retrieves published jobs from public company boards.
    """
    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, timeout: float = 15.0, user_agent: str = "RolePilot-Discovery/1.0"):
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}

    @property
    def provider_name(self) -> str:
        return "greenhouse"

    def parse_job_payload(
        self,
        board_token: str,
        company_name: str,
        raw_job: dict,
    ) -> CanonicalJob:
        """Transforms a single raw Greenhouse job JSON dict into a CanonicalJob."""
        source_job_id = str(raw_job.get("id"))
        title = raw_job.get("title", "").strip()
        job_url = raw_job.get("absolute_url") or f"https://boards.greenhouse.io/{board_token}/jobs/{source_job_id}"

        # Extract location names
        locations: List[str] = []
        loc_obj = raw_job.get("location")
        if loc_obj and isinstance(loc_obj, dict) and loc_obj.get("name"):
            locations.append(loc_obj["name"].strip())

        # Extract offices
        offices: List[str] = []
        for office in raw_job.get("offices") or []:
            if isinstance(office, dict) and office.get("name"):
                offices.append(office["name"].strip())
                if office.get("location") and office["location"] not in locations:
                    locations.append(office["location"].strip())

        # Extract departments
        departments: List[str] = []
        for dept in raw_job.get("departments") or []:
            if isinstance(dept, dict) and dept.get("name"):
                departments.append(dept["name"].strip())

        raw_content = raw_job.get("content") or ""

        updated_at = None
        if raw_job.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(raw_job["updated_at"].replace("Z", "+00:00"))
            except Exception:
                pass

        publication_time = None
        if raw_job.get("first_published"):
            try:
                publication_time = datetime.fromisoformat(raw_job["first_published"].replace("Z", "+00:00"))
            except Exception:
                pass

        now = datetime.now(timezone.utc)
        canonical_id = generate_canonical_job_id("greenhouse", board_token, source_job_id)

        job = CanonicalJob(
            id=canonical_id,
            source="greenhouse",
            source_job_id=source_job_id,
            board_token=board_token,
            company_name=company_name,
            title=title,
            description_raw_html=raw_content,
            description_clean_text="",  # Populated by analyze_job
            job_url=job_url,
            application_url=job_url,
            listed_locations=locations,
            departments=departments,
            offices=offices,
            publication_timestamp=publication_time,
            source_update_timestamp=updated_at,
            first_seen_timestamp=now,
            last_seen_timestamp=now,
            last_verified_timestamp=now,
            content_fingerprint="",  # Populated by analyze_job
        )

        return analyze_job(job)

    async def fetch_jobs(
        self,
        identifier_or_query: str,
        company_name: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        **kwargs
    ) -> ProviderFetchResult:
        """Implements BaseJobProvider.fetch_jobs using board_token."""
        comp_name = company_name or identifier_or_query.capitalize()
        board_token = identifier_or_query.strip().lower()
        url = f"{self.BASE_URL}/{board_token}/jobs?content=true"

        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)
            should_close_client = True

        try:
            response = await client.get(url)
            if response.status_code == 404:
                return ProviderFetchResult(
                    provider_name=self.provider_name,
                    board_or_query=board_token,
                    status="FAILED",
                    error_message=f"Board '{board_token}' not found (HTTP 404).",
                )
            response.raise_for_status()
            data = response.json()
            raw_jobs = data.get("jobs", [])

            canonical_jobs = [
                self.parse_job_payload(board_token, comp_name, rj)
                for rj in raw_jobs
            ]

            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=board_token,
                jobs=canonical_jobs,
                total_found=len(canonical_jobs),
                status="SUCCESS",
            )
        except httpx.HTTPStatusError as e:
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=board_token,
                status="FAILED",
                error_message=f"HTTP Error {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=board_token,
                status="FAILED",
                error_message=f"Network or parsing error: {str(e)}",
            )
        finally:
            if should_close_client:
                await client.aclose()

    # Alias for backward compatibility
    async def fetch_board(self, board_token: str, company_name: str, client: Optional[httpx.AsyncClient] = None):
        return await self.fetch_jobs(identifier_or_query=board_token, company_name=company_name, client=client)
