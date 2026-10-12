import uuid
from django.db import models
from src.schemas.candidate import CandidateProfile


class CanonicalJobModel(models.Model):
    id = models.CharField(max_length=64, primary_key=True, help_text="Deterministic UUID")
    source = models.CharField(max_length=50, default="greenhouse", db_index=True)
    source_job_id = models.CharField(max_length=100)
    board_token = models.CharField(max_length=100, db_index=True)
    company_name = models.CharField(max_length=200, db_index=True)
    title = models.CharField(max_length=300)
    description_raw_html = models.TextField(blank=True, default="")
    description_clean_text = models.TextField(blank=True, default="")
    job_url = models.URLField(max_length=1000)
    application_url = models.URLField(max_length=1000, blank=True, null=True)
    listed_locations = models.JSONField(default=list)
    departments = models.JSONField(default=list)
    offices = models.JSONField(default=list)
    publication_timestamp = models.DateTimeField(null=True, blank=True)
    source_update_timestamp = models.DateTimeField(null=True, blank=True)
    first_seen_timestamp = models.DateTimeField(auto_now_add=True)
    last_seen_timestamp = models.DateTimeField(auto_now=True)
    content_fingerprint = models.CharField(max_length=64, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    work_mode = models.CharField(max_length=20, default="UNKNOWN", db_index=True)
    work_mode_evidence = models.TextField(blank=True, null=True)
    geographic_scope = models.CharField(max_length=30, default="UNKNOWN")
    extracted_skills = models.JSONField(default=list)
    seniority_level = models.CharField(max_length=20, default="UNKNOWN")
    analysis_status = models.CharField(max_length=20, default="PENDING")

    class Meta:
        ordering = ["-first_seen_timestamp"]
        verbose_name = "Canonical Job"
        verbose_name_plural = "Canonical Jobs"

    def __str__(self):
        return f"{self.title} @ {self.company_name} ({self.work_mode})"


class DiscoveryRunModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    max_job_cap = models.IntegerField(default=100)
    total_fetched_raw = models.IntegerField(default=0)
    unique_jobs_collected = models.IntegerField(default=0)
    duplicates_skipped = models.IntegerField(default=0)
    cap_reached = models.BooleanField(default=False)
    eligible_count = models.IntegerField(default=0)
    review_count = models.IntegerField(default=0)
    ineligible_count = models.IntegerField(default=0)
    provider_results = models.JSONField(default=dict)
    errors = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="SUCCESS")

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Discovery Run"
        verbose_name_plural = "Discovery Runs"

    def __str__(self):
        return f"Run {self.started_at.strftime('%Y-%m-%d %H:%M')} — {self.unique_jobs_collected} jobs ({self.status})"


def default_target_titles():
    return [
        "Backend Engineer",
        "Python Engineer",
        "Software Engineer",
        "API Engineer"
    ]


def default_primary_languages():
    return ["Python"]


def default_alternative_languages():
    return ["Go", "Java"]


def default_required_skills():
    return ["PostgreSQL", "REST API"]


def default_preferred_skills():
    return ["FastAPI", "Django", "Docker", "Redis", "Kubernetes"]


def default_excluded_keywords():
    return ["Wordpress", "PHP", "Sales", "Data Entry"]


class CandidateProfileModel(models.Model):
    id = models.CharField(max_length=64, primary_key=True, default="default-candidate")
    name = models.CharField(max_length=100, default="Aditya")
    home_country = models.CharField(max_length=2, default="IN")
    home_city = models.CharField(max_length=100, blank=True, default="Bengaluru")
    target_titles = models.JSONField(default=default_target_titles)
    primary_languages = models.JSONField(default=default_primary_languages)
    alternative_languages = models.JSONField(default=default_alternative_languages)
    required_skills = models.JSONField(default=default_required_skills)
    preferred_skills = models.JSONField(default=default_preferred_skills)
    excluded_keywords = models.JSONField(default=default_excluded_keywords)
    min_seniority = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Candidate Profile"
        verbose_name_plural = "Candidate Profiles"

    def __str__(self):
        return f"{self.name} ({self.home_city or ''}, {self.home_country})"

    def to_pydantic(self) -> CandidateProfile:
        return CandidateProfile(
            id=self.id,
            name=self.name,
            home_country=self.home_country,
            home_city=self.home_city,
            target_titles=self.target_titles or [],
            primary_languages=self.primary_languages or [],
            alternative_languages=self.alternative_languages or [],
            required_skills=self.required_skills or [],
            preferred_skills=self.preferred_skills or [],
            excluded_keywords=self.excluded_keywords or [],
            min_seniority=self.min_seniority,
        )


class CandidateJobMatchModel(models.Model):
    id = models.CharField(max_length=128, primary_key=True)
    candidate = models.ForeignKey(CandidateProfileModel, on_delete=models.CASCADE, related_name="matches")
    job = models.ForeignKey(CanonicalJobModel, on_delete=models.CASCADE, related_name="matches")
    relevance_score = models.FloatField(default=0.0, db_index=True)
    recommendation = models.CharField(max_length=20, default="REVIEW", db_index=True)
    eligibility_status = models.CharField(max_length=30, default="NEEDS_VERIFICATION", db_index=True)
    eligibility_reason = models.TextField(blank=True, default="")
    matched_titles = models.JSONField(default=list)
    matched_languages = models.JSONField(default=list)
    matched_skills = models.JSONField(default=list)
    missing_skills = models.JSONField(default=list)
    exclusion_reasons = models.JSONField(default=list)
    explanation = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-relevance_score", "-updated_at"]
        verbose_name = "Candidate Job Match"
        verbose_name_plural = "Candidate Job Matches"

    def __str__(self):
        return f"[{self.recommendation}] {self.relevance_score:.1f} | {self.job.title} @ {self.job.company_name}"
