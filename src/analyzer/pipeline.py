from src.schemas.job import CanonicalJob, AnalysisStatus
from .cleaner import unescape_and_clean_html
from .work_mode import classify_work_mode
from .skills import extract_skills_and_seniority


def analyze_job(job: CanonicalJob) -> CanonicalJob:
    """
    Applies the full analysis pipeline to a CanonicalJob:
    - HTML decoding & stripping
    - Content fingerprint generation
    - Work mode classification & evidence collection
    - Skill and seniority extraction
    """
    try:
        decoded_html, clean_text, fingerprint = unescape_and_clean_html(job.description_raw_html)
        job.description_raw_html = decoded_html
        job.description_clean_text = clean_text
        job.content_fingerprint = fingerprint

        # Work Mode
        work_mode, evidence = classify_work_mode(
            title=job.title,
            listed_locations=job.listed_locations,
            description_text=clean_text
        )
        job.work_mode = work_mode
        job.work_mode_evidence = evidence

        # Skills and Seniority
        skills, seniority = extract_skills_and_seniority(
            title=job.title,
            text=clean_text
        )
        job.extracted_skills = skills
        job.seniority_level = seniority

        job.analysis_status = AnalysisStatus.ANALYZED
    except Exception as e:
        job.analysis_status = AnalysisStatus.FAILED
        job.work_mode_evidence = f"Analysis failed: {str(e)}"

    return job
