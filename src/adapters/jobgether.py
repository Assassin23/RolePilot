import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
import httpx

from src.schemas.job import CanonicalJob, generate_canonical_job_id
from src.analyzer.pipeline import analyze_job
from src.adapters.base import BaseJobProvider, ProviderFetchResult

logger = logging.getLogger(__name__)


class JobgetherAdapter(BaseJobProvider):
    """
    Adapter for Jobgether Job Search API (https://jobgether.com/developers).
    - Public API: No API key required.
    - Rate Control: Strictly capped at 100 jobs / 4 API calls per day (page 1 to 4, limit=25).
    - Daily Persistence: Results are cached daily to disk; cannot be re-queried on the same day.
    """
    BASE_URL = "https://jobgether.com/api/v1/jobs"
    MAX_DAILY_JOBS = 100
    PAGE_SIZE = 25
    MAX_PAGES = 4  # 4 calls * 25 jobs = 100 jobs max

    def __init__(
        self,
        enabled: bool = True,
        cache_dir: str | Path = ".cache",
        timeout: float = 15.0,
    ):
        self.enabled = enabled
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "jobgether_daily_cache.json"
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "RolePilot-Discovery/1.0",
        }

    @property
    def provider_name(self) -> str:
        return "jobgether"

    def _get_today_date_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """Loads cached responses from disk if available."""
        if not self.cache_file.exists():
            return None
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read Jobgether cache: {e}")
            return None

    def _save_cache(self, raw_jobs: List[dict], query: str, calls_made: int) -> None:
        """Saves fetched job payloads to disk with today's date stamp."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "date": self._get_today_date_str(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "api_calls_made": calls_made,
            "jobs_count": len(raw_jobs),
            "raw_jobs": raw_jobs,
        }
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write Jobgether cache: {e}")

    def parse_job_payload(self, raw_job: dict) -> CanonicalJob:
        """Parses a Jobgether API job JSON object into a CanonicalJob."""
        source_job_id = str(raw_job.get("id") or raw_job.get("_id") or raw_job.get("jobId") or "")
        title = raw_job.get("title", "").strip()
        
        company = "Unknown"
        comp_val = raw_job.get("company")
        if isinstance(comp_val, dict):
            company = comp_val.get("name") or "Unknown"
        elif isinstance(comp_val, str) and comp_val:
            company = comp_val.strip()

        job_url = raw_job.get("url") or raw_job.get("applyUrl") or "https://jobgether.com"
        apply_url = raw_job.get("applyUrl") or raw_job.get("apply_url")

        locations = []
        loc_val = raw_job.get("location") or raw_job.get("locations")
        if isinstance(loc_val, str) and loc_val:
            locations.append(loc_val.strip())
        elif isinstance(loc_val, list):
            locations.extend(str(l).strip() for l in loc_val if l)
        elif isinstance(loc_val, dict):
            name = loc_val.get("name") or loc_val.get("country") or loc_val.get("city")
            if name:
                locations.append(name.strip())

        raw_desc = raw_job.get("description") or raw_job.get("content") or ""
        now = datetime.now(timezone.utc)
        canonical_id = generate_canonical_job_id("jobgether", "api", source_job_id)

        job = CanonicalJob(
            id=canonical_id,
            source="jobgether",
            source_job_id=source_job_id,
            board_token="jobgether_api",
            company_name=company,
            title=title,
            description_raw_html=raw_desc,
            description_clean_text="",
            job_url=job_url,
            application_url=apply_url,
            listed_locations=locations,
            first_seen_timestamp=now,
            last_seen_timestamp=now,
            last_verified_timestamp=now,
            content_fingerprint="",
        )
        return analyze_job(job)

    async def fetch_jobs(
        self,
        identifier_or_query: str,
        client: Optional[httpx.AsyncClient] = None,
        force_refresh: bool = False,
        **kwargs
    ) -> ProviderFetchResult:
        """
        Fetches up to 100 jobs across max 4 pages (limit=25).
        Enforces a strict 1-run-per-day rate limit using persistent disk caching.
        """
        if not self.enabled:
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=identifier_or_query,
                status="FAILED",
                error_message="Jobgether provider is disabled.",
            )

        today_str = self._get_today_date_str()
        cache = self._load_cache()

        # Step 1: Check if already executed today
        if cache and cache.get("date") == today_str and not force_refresh:
            cached_raw = cache.get("raw_jobs", [])
            logger.info(f"Jobgether: Daily limit reached for {today_str}. Returning {len(cached_raw)} cached jobs.")
            canonical_jobs = [self.parse_job_payload(rj) for rj in cached_raw]
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=identifier_or_query,
                jobs=canonical_jobs,
                total_found=len(canonical_jobs),
                status="SUCCESS",
                error_message=f"Served from daily cache ({today_str}). Daily limit of 4 calls / 100 jobs respected."
            )

        # Step 2: Query up to 4 pages (limit=25) to retrieve max 100 jobs
        all_raw_jobs: List[dict] = []
        calls_made = 0
        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)
            should_close_client = True

        try:
            for page in range(1, self.MAX_PAGES + 1):
                params = {
                    "keyword": identifier_or_query,
                    "limit": self.PAGE_SIZE,
                    "page": page,
                }
                calls_made += 1
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
                items = data.get("data") or data.get("jobs") or []
                if not items:
                    break

                all_raw_jobs.extend(items)

                # Stop if pagination indicates no more pages or fewer than page size returned
                has_more = data.get("pagination", {}).get("hasMore")
                if has_more is False or len(items) < self.PAGE_SIZE:
                    break

            # Step 3: Persistently cache results for today
            self._save_cache(all_raw_jobs, identifier_or_query, calls_made)

            canonical_jobs = [self.parse_job_payload(rj) for rj in all_raw_jobs]
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=identifier_or_query,
                jobs=canonical_jobs,
                total_found=len(canonical_jobs),
                status="SUCCESS",
            )
        except Exception as e:
            logger.error(f"Jobgether fetch error: {e}")
            # If network error occurs but we have prior cache, fall back to it
            if cache and cache.get("raw_jobs"):
                cached_raw = cache.get("raw_jobs", [])
                canonical_jobs = [self.parse_job_payload(rj) for rj in cached_raw]
                return ProviderFetchResult(
                    provider_name=self.provider_name,
                    board_or_query=identifier_or_query,
                    jobs=canonical_jobs,
                    total_found=len(canonical_jobs),
                    status="SUCCESS",
                    error_message=f"Network error ({str(e)}). Fallback to cached results from {cache.get('date')}."
                )
            return ProviderFetchResult(
                provider_name=self.provider_name,
                board_or_query=identifier_or_query,
                status="FAILED",
                error_message=f"Jobgether fetch failed: {str(e)}",
            )
        finally:
            if should_close_client:
                await client.aclose()
