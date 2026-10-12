import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.management import call_command
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse

from jobs.models import (
    CanonicalJobModel,
    DiscoveryRunModel,
    CandidateProfileModel,
    CandidateJobMatchModel,
)
from jobs.services import get_or_create_default_profile
from jobs.tasks import async_discover_jobs, async_inspect_and_discover


from pathlib import Path
import yaml

def _get_active_boards():
    config_path = Path("config/boards.yaml")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data.get("boards", [])
        except Exception:
            return []
    return []


def dashboard_view(request):
    """Main discovery dashboard and match review interface."""
    profile = get_or_create_default_profile()

    # Filters
    rec_filter = request.GET.get("rec", "all")
    mode_filter = request.GET.get("mode", "all")
    source_filter = request.GET.get("source", "all")
    search_query = request.GET.get("q", "").strip().lower()

    matches_qs = CandidateJobMatchModel.objects.filter(candidate=profile).select_related("job")

    if rec_filter != "all":
        matches_qs = matches_qs.filter(recommendation=rec_filter)
    if mode_filter != "all":
        matches_qs = matches_qs.filter(job__work_mode=mode_filter)
    if source_filter != "all":
        matches_qs = matches_qs.filter(job__source=source_filter)
    if search_query:
        matches_qs = [
            m for m in matches_qs
            if search_query in m.job.title.lower()
            or search_query in m.job.company_name.lower()
            or any(search_query in s.lower() for s in m.job.extracted_skills)
        ]

    # Metrics
    all_candidate_matches = CandidateJobMatchModel.objects.filter(candidate=profile)
    total_jobs = CanonicalJobModel.objects.count()
    match_count = all_candidate_matches.filter(recommendation="MATCH").count()
    review_count = all_candidate_matches.filter(recommendation="REVIEW").count()
    exclude_count = all_candidate_matches.filter(recommendation="EXCLUDE").count()
    latest_run = DiscoveryRunModel.objects.first()
    active_run = DiscoveryRunModel.objects.filter(status="RUNNING").first()
    boards = _get_active_boards()
    enabled_boards = [b for b in boards if b.get("enabled", True)]

    context = {
        "profile": profile,
        "matches": matches_qs,
        "total_jobs": total_jobs,
        "match_count": match_count,
        "review_count": review_count,
        "exclude_count": exclude_count,
        "latest_run": latest_run,
        "active_run": active_run,
        "is_running": bool(active_run),
        "rec_filter": rec_filter,
        "mode_filter": mode_filter,
        "source_filter": source_filter,
        "search_query": search_query,
        "boards": boards,
        "enabled_boards_count": len(enabled_boards),
    }
    return render(request, "dashboard.html", context)


logger = logging.getLogger(__name__)


def trigger_discovery_view(request):
    """Triggers discovery execution asynchronously in background."""
    if request.method == "POST":
        mode = request.POST.get("mode", "live")
        is_live = (mode == "live")
        try:
            run_record = DiscoveryRunModel.objects.create(
                status="RUNNING",
                max_job_cap=100,
                provider_results={"info": f"Initiating {'LIVE' if is_live else 'MOCK'} background discovery..."},
            )
            async_discover_jobs(is_live=is_live, cap=100, run_id=str(run_record.id))
            messages.info(
                request,
                f"⚡ Job discovery running in the background ({'LIVE' if is_live else 'MOCK'} mode). Dashboard will auto-update as jobs arrive!"
            )
        except Exception as e:
            logger.exception("Discovery run encountered an error")
            messages.error(request, f"Discovery run error: {str(e)}")

    return redirect("dashboard")


def trigger_board_inspection_view(request):
    """
    Triggers ATS board inspection (from catalog or custom URL) in background,
    registers verified boards in config/boards.yaml, and cascades to discovery.
    """
    if request.method == "POST":
        action = request.POST.get("action", "catalog")
        then_discover = request.POST.get("then_discover") == "true"

        try:
            limit_str = request.POST.get("limit", "10").strip()
            limit = int(limit_str) if limit_str.isdigit() and int(limit_str) > 0 else None
            url = request.POST.get("url", "").strip()
            name = request.POST.get("name", "").strip()

            if action == "single" and not url:
                messages.error(request, "Please enter a valid career page URL to inspect.")
                return redirect("dashboard")

            info_label = f"Catalog ({limit or 100} companies)" if action == "catalog" else url
            run_record = DiscoveryRunModel.objects.create(
                status="RUNNING",
                max_job_cap=100,
                provider_results={"info": f"Inspecting {info_label}..."},
            )

            async_inspect_and_discover(
                action=action,
                limit=limit,
                url=url,
                name=name,
                then_discover=then_discover,
                run_id=str(run_record.id),
            )

            messages.info(
                request,
                f"🔍 Background board inspection & job harvest started for {info_label}! Processing in background..."
            )

        except Exception as e:
            logger.exception("Board inspection or discovery error")
            messages.error(request, f"Inspection or discovery error: {str(e)}")

    return redirect("dashboard")


def discovery_status_api(request):
    """Returns current discovery status as JSON for live UI polling."""
    latest = DiscoveryRunModel.objects.first()
    is_running = (latest.status == "RUNNING") if latest else False
    return JsonResponse({
        "is_running": is_running,
        "status": latest.status if latest else "IDLE",
        "unique_jobs_collected": latest.unique_jobs_collected if latest else 0,
        "eligible_count": latest.eligible_count if latest else 0,
        "review_count": latest.review_count if latest else 0,
        "total_jobs": CanonicalJobModel.objects.count(),
        "errors": latest.errors if latest else [],
    })





def runs_view(request):
    """View history of discovery runs and provider telemetry."""
    runs = DiscoveryRunModel.objects.all()[:20]
    return render(request, "runs.html", {"runs": runs})


def profile_view(request):
    """View and update candidate preferences."""
    profile = get_or_create_default_profile()

    if request.method == "POST":
        profile.name = request.POST.get("name", profile.name).strip()
        profile.home_country = request.POST.get("home_country", profile.home_country).strip().upper()
        profile.home_city = request.POST.get("home_city", profile.home_city).strip()
        
        # Parse comma-separated inputs
        titles_raw = request.POST.get("target_titles", "")
        profile.target_titles = [t.strip() for t in titles_raw.split(",") if t.strip()]

        primary_raw = request.POST.get("primary_languages", "")
        profile.primary_languages = [l.strip() for l in primary_raw.split(",") if l.strip()]

        alt_raw = request.POST.get("alternative_languages", "")
        profile.alternative_languages = [l.strip() for l in alt_raw.split(",") if l.strip()]

        req_raw = request.POST.get("required_skills", "")
        profile.required_skills = [s.strip() for s in req_raw.split(",") if s.strip()]

        pref_raw = request.POST.get("preferred_skills", "")
        profile.preferred_skills = [s.strip() for s in pref_raw.split(",") if s.strip()]

        excl_raw = request.POST.get("excluded_keywords", "")
        profile.excluded_keywords = [e.strip() for e in excl_raw.split(",") if e.strip()]

        profile.save()
        messages.success(request, "Candidate profile and matching preferences updated!")
        return redirect("profile")

    return render(request, "profile.html", {"profile": profile})


def job_detail_view(request, job_id):
    """Detail view for a canonical job posting."""
    job = get_object_or_404(CanonicalJobModel, id=job_id)
    profile = get_or_create_default_profile()
    match = CandidateJobMatchModel.objects.filter(candidate=profile, job=job).first()
    return render(request, "job_detail.html", {"job": job, "match": match})
