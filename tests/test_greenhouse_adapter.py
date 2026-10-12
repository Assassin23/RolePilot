import json
from pathlib import Path
import httpx
import pytest

from src.adapters.greenhouse import GreenhouseAdapter
from src.schemas.job import WorkMode, AnalysisStatus


@pytest.fixture
def mock_jobs_payload():
    fixture_path = Path("tests/fixtures/greenhouse_mock_jobs.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_fetch_board_success(mock_jobs_payload):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "gitlab/jobs" in str(request.url)
        return httpx.Response(200, json=mock_jobs_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = GreenhouseAdapter()
        result = await adapter.fetch_board(
            board_token="gitlab",
            company_name="GitLab",
            client=client
        )

    assert result.status == "SUCCESS"
    assert result.total_found == 3
    assert len(result.jobs) == 3

    # Check first job: Senior Backend Engineer
    job1 = result.jobs[0]
    assert job1.board_token == "gitlab"
    assert job1.company_name == "GitLab"
    assert job1.source_job_id == "8860302001"
    assert job1.work_mode == WorkMode.REMOTE
    assert job1.seniority_level == "SENIOR"
    assert "Python" in job1.extracted_skills
    assert "Django" in job1.extracted_skills
    assert "FastAPI" in job1.extracted_skills
    assert "PostgreSQL" in job1.extracted_skills
    assert job1.analysis_status == AnalysisStatus.ANALYZED
    assert len(job1.content_fingerprint) == 64

    # Check second job: Hybrid Software Engineer
    job2 = result.jobs[1]
    assert job2.work_mode == WorkMode.HYBRID
    assert "Redis" in job2.extracted_skills

    # Check third job: Junior on-site
    job3 = result.jobs[2]
    assert job3.seniority_level == "JUNIOR"
    assert job3.work_mode == WorkMode.ONSITE


@pytest.mark.asyncio
async def test_fetch_board_404_isolation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not Found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = GreenhouseAdapter()
        result = await adapter.fetch_board(
            board_token="non_existent_company_xyz",
            company_name="NonExistent",
            client=client
        )

    # Must NOT raise exception; must isolate error cleanly
    assert result.status == "FAILED"
    assert result.total_found == 0
    assert len(result.jobs) == 0
    assert "404" in result.error_message


@pytest.mark.asyncio
async def test_fetch_board_server_error_isolation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = GreenhouseAdapter()
        result = await adapter.fetch_board(
            board_token="flakey_board",
            company_name="FlakeyCorp",
            client=client
        )

    assert result.status == "FAILED"
    assert "500" in result.error_message
