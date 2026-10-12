from django.contrib import admin
from jobs.models import (
    CanonicalJobModel,
    DiscoveryRunModel,
    CandidateProfileModel,
    CandidateJobMatchModel,
)


@admin.register(CanonicalJobModel)
class CanonicalJobAdmin(admin.ModelAdmin):
    list_display = ("title", "company_name", "source", "work_mode", "first_seen_timestamp", "is_active")
    list_filter = ("source", "work_mode", "is_active", "seniority_level")
    search_fields = ("title", "company_name", "description_clean_text")
    readonly_fields = ("id", "content_fingerprint", "first_seen_timestamp", "last_seen_timestamp")


@admin.register(DiscoveryRunModel)
class DiscoveryRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "status", "unique_jobs_collected", "duplicates_skipped", "cap_reached")
    list_filter = ("status", "cap_reached")
    readonly_fields = ("id", "started_at", "completed_at")


@admin.register(CandidateProfileModel)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "home_country", "home_city", "is_active", "updated_at")


@admin.register(CandidateJobMatchModel)
class CandidateJobMatchAdmin(admin.ModelAdmin):
    list_display = ("job", "candidate", "relevance_score", "recommendation", "eligibility_status")
    list_filter = ("recommendation", "eligibility_status")
    search_fields = ("job__title", "job__company_name", "explanation")
