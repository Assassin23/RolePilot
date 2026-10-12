from datetime import datetime, timezone
from src.schemas.job import CanonicalJob, WorkMode
from src.schemas.candidate import CandidateProfile, EligibilityStatus
from src.matcher.geo_eligibility import evaluate_location_eligibility


def make_test_job(title: str, locations: list, text: str, work_mode: WorkMode) -> CanonicalJob:
    now = datetime.now(timezone.utc)
    return CanonicalJob(
        id="test-job-1",
        source="test",
        source_job_id="123",
        board_token="test_board",
        company_name="TestCorp",
        title=title,
        description_raw_html="",
        description_clean_text=text,
        job_url="https://example.com/jobs/1",
        listed_locations=locations,
        first_seen_timestamp=now,
        last_seen_timestamp=now,
        last_verified_timestamp=now,
        content_fingerprint="abc",
        work_mode=work_mode,
    )


def test_onsite_same_city_eligible():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Backend Engineer",
        locations=["Bengaluru, India"],
        text="On-site in Bengaluru office.",
        work_mode=WorkMode.ONSITE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.ELIGIBLE
    assert "Bengaluru" in reason


def test_onsite_different_city_needs_verification():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Backend Engineer",
        locations=["Pune, India"],
        text="On-site in Pune office.",
        work_mode=WorkMode.ONSITE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.NEEDS_VERIFICATION
    assert "Pune" in reason or "city" in reason


def test_onsite_different_country_ineligible():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Backend Engineer",
        locations=["London, UK"],
        text="On-site in London.",
        work_mode=WorkMode.ONSITE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.INELIGIBLE


def test_remote_india_eligible():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Python Engineer (Remote)",
        locations=["Remote, India"],
        text="Remote work from anywhere in India.",
        work_mode=WorkMode.REMOTE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.ELIGIBLE
    assert "India" in reason or candidate.home_country in reason


def test_remote_worldwide_eligible():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Software Engineer",
        locations=["Remote"],
        text="We are an all-remote team. Work from anywhere in the world.",
        work_mode=WorkMode.REMOTE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.ELIGIBLE
    assert "anywhere" in reason.lower() or "worldwide" in reason.lower()


def test_remote_us_only_ineligible_for_india():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Staff Backend Engineer",
        locations=["Remote"],
        text="Remote position. Candidates must reside in the US only and be eligible to work in the US.",
        work_mode=WorkMode.REMOTE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.INELIGIBLE
    assert "restricted" in reason.lower() or "us" in reason.lower()


def test_remote_unspecified_bounds_needs_verification():
    candidate = CandidateProfile(home_country="IN", home_city="Bengaluru")
    job = make_test_job(
        title="Software Engineer",
        locations=["Remote"],
        text="Build scalable web applications. Competitive salary and benefits.",
        work_mode=WorkMode.REMOTE,
    )
    status, reason = evaluate_location_eligibility(job, candidate)
    assert status == EligibilityStatus.NEEDS_VERIFICATION
    assert "bounds" in reason.lower() or "verification" in reason.lower()
