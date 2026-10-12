from datetime import datetime, timezone
from src.schemas.job import CanonicalJob, WorkMode
from src.schemas.candidate import CandidateProfile, Recommendation
from src.matcher.relevance import evaluate_candidate_match, detect_languages_in_text


def make_job(title: str, text: str, locations=None, work_mode=WorkMode.REMOTE) -> CanonicalJob:
    now = datetime.now(timezone.utc)
    return CanonicalJob(
        id="job-1",
        source="test",
        source_job_id="1",
        board_token="test",
        company_name="TestCorp",
        title=title,
        description_raw_html="",
        description_clean_text=text,
        job_url="https://example.com/job/1",
        listed_locations=locations or ["Remote, India"],
        first_seen_timestamp=now,
        last_seen_timestamp=now,
        last_verified_timestamp=now,
        content_fingerprint="fp1",
        work_mode=work_mode,
        extracted_skills=["Python", "FastAPI", "PostgreSQL", "REST API", "Docker"],
    )


def test_detect_languages():
    text = "We use Python for microservices, Go for high-throughput streaming, and some Java legacy systems."
    langs = detect_languages_in_text(text)
    assert "Python" in langs
    assert "Go" in langs
    assert "Java" in langs


def test_primary_language_high_match():
    candidate = CandidateProfile(
        home_country="IN",
        primary_languages=["Python"],
        alternative_languages=["Go"],
        required_skills=["PostgreSQL", "REST API"],
        preferred_skills=["Docker", "FastAPI"],
    )
    job = make_job(
        title="Backend Engineer, Python",
        text="Build APIs in Python with FastAPI, PostgreSQL, and Docker."
    )
    result = evaluate_candidate_match(job, candidate)

    assert result.recommendation == Recommendation.MATCH
    assert result.relevance_score >= 70.0
    assert "Python" in result.matched_languages
    assert "PostgreSQL" in result.matched_skills


def test_alternative_language_acceptable_match():
    candidate = CandidateProfile(
        home_country="IN",
        primary_languages=["Python"],
        alternative_languages=["Java", "Go"],
    )
    # Job requires Java or Go, but not Python
    job = make_job(
        title="Backend Software Engineer",
        text="Building distributed storage in Go and Java. Experience with PostgreSQL."
    )
    job.extracted_skills = ["PostgreSQL", "REST API"]
    result = evaluate_candidate_match(job, candidate)

    # Alternate language should still qualify for REVIEW or MATCH, not EXCLUDE
    assert result.recommendation in (Recommendation.MATCH, Recommendation.REVIEW)
    assert any(lang in result.matched_languages for lang in ["Go", "Java"])


def test_excluded_keywords_immediate_disqualification():
    candidate = CandidateProfile(
        home_country="IN",
        excluded_keywords=["Wordpress", "PHP"],
    )
    job = make_job(
        title="Python and Wordpress Developer",
        text="Maintain our Wordpress blog and Python scripts."
    )
    result = evaluate_candidate_match(job, candidate)

    assert result.recommendation == Recommendation.EXCLUDE
    assert result.relevance_score == 0.0
    assert any("Wordpress" in reason for reason in result.exclusion_reasons)


def test_human_languages_ignored():
    """Ensure English or German mentions do not penalize or filter technical matching."""
    candidate = CandidateProfile(home_country="IN", primary_languages=["Python"])
    job = make_job(
        title="Python Engineer",
        text="Fluent English required. Knowledge of German is a plus. Python and REST API development."
    )
    result = evaluate_candidate_match(job, candidate)
    assert result.recommendation == Recommendation.MATCH
    assert "Python" in result.matched_languages
