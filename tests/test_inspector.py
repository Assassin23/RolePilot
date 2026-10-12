import pytest
import httpx

from inspector.ssrf import validate_safe_url
from inspector.detector import detect_ats_signature, ATSProvider
from inspector.probers.greenhouse import probe_greenhouse_board
from inspector.main import app


def test_ssrf_disallows_private_and_metadata_ips():
    # Loopback
    with pytest.raises(ValueError, match="resolves to private/disallowed IP"):
        validate_safe_url("http://127.0.0.1/careers")

    with pytest.raises(ValueError, match="resolves to private/disallowed IP"):
        validate_safe_url("http://localhost/careers")

    # Cloud metadata
    with pytest.raises(ValueError, match="resolves to private/disallowed IP"):
        validate_safe_url("http://169.254.169.254/latest/meta-data/")

    # Disallowed scheme
    with pytest.raises(ValueError, match="Disallowed scheme"):
        validate_safe_url("ftp://example.com/careers")

    # Embedded credentials
    with pytest.raises(ValueError, match="embedded user credentials"):
        validate_safe_url("http://admin:pass@example.com/careers")


def test_detector_identifies_greenhouse_embed():
    html = """
    <html>
        <body>
            <h1>Careers at Cloudflare</h1>
            <script src="https://boards.greenhouse.io/embed/job_board.js?for=cloudflare"></script>
        </body>
    </html>
    """
    ats, slug, evidence = detect_ats_signature("https://www.cloudflare.com/careers/", html)
    assert ats == ATSProvider.GREENHOUSE
    assert slug == "cloudflare"
    assert "Greenhouse" in evidence


def test_detector_identifies_greenhouse_hosted_link():
    html = """
    <div>
        <a href="https://job-boards.greenhouse.io/gitlab">Browse Open Positions</a>
    </div>
    """
    ats, slug, _ = detect_ats_signature("https://about.gitlab.com/jobs/", html)
    assert ats == ATSProvider.GREENHOUSE
    assert slug == "gitlab"


def test_detector_identifies_lever():
    html = '<div><a href="https://jobs.lever.co/netflix">View Jobs</a></div>'
    ats, slug, _ = detect_ats_signature("https://jobs.netflix.com/", html)
    assert ats == ATSProvider.LEVER
    assert slug == "netflix"


def test_detector_identifies_ashby():
    html = '<div><a href="https://jobs.ashbyhq.com/openai">View Jobs</a></div>'
    ats, slug, _ = detect_ats_signature("https://openai.com/careers", html)
    assert ats == ATSProvider.ASHBY
    assert slug == "openai"


def test_detector_identifies_workday():
    html = '<div><a href="https://adobe.wd5.myworkdayjobs.com/external">Apply</a></div>'
    ats, slug, _ = detect_ats_signature("https://adobe.com/careers", html)
    assert ats == ATSProvider.WORKDAY
    assert slug == "adobe"


@pytest.mark.asyncio
async def test_greenhouse_prober_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "boards-api.greenhouse.io/v1/boards/gitlab/jobs" in str(request.url)
        return httpx.Response(200, json={"jobs": [{"id": 1}], "meta": {"total": 42}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        is_ok, count, endpoint, evidence = await probe_greenhouse_board("gitlab", client=client)

    assert is_ok is True
    assert count == 42
    assert "gitlab" in endpoint
    assert "42 published jobs" in evidence


@pytest.mark.asyncio
async def test_inspector_api_ssrf_rejection():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/inspect",
            json={"company_name": "Internal Corp", "careers_url": "http://127.0.0.1/careers"}
        )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ERROR"
    assert "private/disallowed IP" in data["evidence"]


@pytest.mark.asyncio
async def test_catalog_endpoint_returns_100_companies():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/catalog")
    assert res.status_code == 200
    catalog = res.json()
    assert len(catalog) == 100
    assert catalog[0]["name"] == "Anthropic"
    assert "careers_url" in catalog[0]
    assert "slug_hint" in catalog[0]


@pytest.mark.asyncio
async def test_batch_verify_catalog_with_limit():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/catalog/verify", json={"limit": 2, "concurrency": 2})
    assert res.status_code == 200
    data = res.json()
    assert data["total_inspected"] == 2
    assert "results" in data
    assert len(data["results"]) == 2

