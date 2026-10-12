import json
from pathlib import Path
import httpx
import pytest

from src.adapters.jobgether import JobgetherAdapter
from src.schemas.job import CanonicalJob


def test_jobgether_parse_job_payload(tmp_path):
    adapter = JobgetherAdapter(enabled=True, cache_dir=tmp_path)
    mock_item = {
        "id": "jg_12345",
        "title": "Senior Python Backend Engineer",
        "company": {"name": "TechScale"},
        "url": "https://jobgether.com/job/12345",
        "applyUrl": "https://company.com/apply",
        "locations": ["Remote", "India"],
        "description": "<p>Looking for a Senior Python developer with FastAPI and PostgreSQL experience. 100% remote.</p>",
    }

    job = adapter.parse_job_payload(mock_item)

    assert isinstance(job, CanonicalJob)
    assert job.source == "jobgether"
    assert job.source_job_id == "jg_12345"
    assert job.company_name == "TechScale"
    assert "Python" in job.extracted_skills
    assert "FastAPI" in job.extracted_skills
    assert job.work_mode.value == "REMOTE"
    assert len(job.content_fingerprint) == 64


@pytest.mark.asyncio
async def test_jobgether_4_calls_daily_cap_and_caching(tmp_path):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        page = int(request.url.params.get("page", 1))
        # Return 25 items per page for pages 1..4
        items = [
            {"id": f"job_p{page}_{i}", "title": f"Python Dev {page}-{i}", "company": "Co", "url": "https://j.com"}
            for i in range(25)
        ]
        return httpx.Response(200, json={"data": items, "pagination": {"hasMore": True}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = JobgetherAdapter(enabled=True, cache_dir=tmp_path)
        
        # 1st run: Should make exactly 4 calls (25 items * 4 = 100 jobs)
        result1 = await adapter.fetch_jobs("python", client=client)
        assert result1.status == "SUCCESS"
        assert result1.total_found == 100
        assert len(result1.jobs) == 100
        assert call_count == 4

        # Verify cache file was written
        cache_file = tmp_path / "jobgether_daily_cache.json"
        assert cache_file.exists()
        with open(cache_file, "r") as f:
            cache_data = json.load(f)
            assert cache_data["jobs_count"] == 100
            assert cache_data["api_calls_made"] == 4

        # 2nd run on same day: MUST use cache and NOT make any more HTTP calls!
        result2 = await adapter.fetch_jobs("python", client=client)
        assert result2.status == "SUCCESS"
        assert result2.total_found == 100
        assert call_count == 4  # NO additional calls made!
        assert "daily cache" in result2.error_message.lower()
