import re
from typing import List, Tuple
from src.schemas.job import CanonicalJob
from src.schemas.candidate import CandidateProfile, CandidateMatchResult, Recommendation
from .geo_eligibility import evaluate_location_eligibility


# Known programming languages to detect
PROGRAMMING_LANGUAGES = {
    "Python": [r"\bpython\b"],
    "Java": [r"\bjava\b(?!\s*script)"],
    "C#": [r"\bc#\b", r"\bcsharp\b", r"\b\.net\b"],
    "C++": [r"\bc\+\+\b"],
    "Go": [r"\bgolang\b", r"\bgo\s+language\b", r"\bgo\b(?!\s+(?:to|ahead|live|on|through))"],
    "Rust": [r"\brust\b"],
    "TypeScript": [r"\btypescript\b", r"\bts\b"],
    "JavaScript": [r"\bjavascript\b", r"\bjs\b", r"\bnode(?:\.js)?\b"],
    "Ruby": [r"\bruby\b", r"\brails\b"],
    "PHP": [r"\bphp\b"],
    "Kotlin": [r"\bkotlin\b"],
    "Scala": [r"\bscala\b"],
    "Swift": [r"\bswift\b"],
}


def detect_languages_in_text(text: str) -> List[str]:
    """Detects programming languages mentioned in job title/text."""
    detected = []
    for lang, patterns in PROGRAMMING_LANGUAGES.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                detected.append(lang)
                break
    return detected


def evaluate_candidate_match(
    job: CanonicalJob,
    candidate: CandidateProfile,
) -> CandidateMatchResult:
    """
    Evaluates candidate-specific technical fit and location eligibility.
    Combines:
    1. Geographic eligibility (ELIGIBLE, INELIGIBLE, NEEDS_VERIFICATION)
    2. Excluded keyword check (Immediate EXCLUDE)
    3. Title relevance (0 - 35 pts)
    4. Programming language match (0 - 35 pts, supports primary & alternate stacks)
    5. Required and preferred skills match (0 - 30 pts)
    """
    job_full_text = f"{job.title}\n{job.description_clean_text}"
    exclusion_reasons: List[str] = []

    # 1. Geographic Eligibility
    eligibility_status, eligibility_reason = evaluate_location_eligibility(job, candidate)

    # 2. Excluded Keywords Check
    for excluded in candidate.excluded_keywords:
        pattern = rf"\b{re.escape(excluded)}\b"
        if re.search(pattern, job_full_text, re.IGNORECASE):
            exclusion_reasons.append(f"Contains excluded keyword: '{excluded}'")

    if exclusion_reasons:
        return CandidateMatchResult(
            candidate_id=candidate.id,
            job_id=job.id,
            relevance_score=0.0,
            recommendation=Recommendation.EXCLUDE,
            eligibility_status=eligibility_status,
            eligibility_reason=eligibility_reason,
            exclusion_reasons=exclusion_reasons,
            explanation=f"Excluded: {', '.join(exclusion_reasons)}."
        )

    # 3. Title Matching (up to 35 pts)
    title_score = 0.0
    matched_titles = []
    job_title_lower = job.title.lower()
    for target in candidate.target_titles:
        if target.lower() in job_title_lower:
            title_score = 35.0
            matched_titles.append(target)
            break
        # Partial match (e.g. "Software Engineer" when target is "Software Engineer - Python")
        words = set(target.lower().split())
        if words.intersection(set(job_title_lower.split())):
            if title_score < 25.0:
                title_score = 25.0
                matched_titles.append(target)

    # 4. Programming Language Stack Matching (up to 35 pts)
    detected_languages = detect_languages_in_text(job_full_text)
    matched_languages = []
    language_score = 0.0

    # Primary language match
    primary_matched = [lang for lang in candidate.primary_languages if lang in detected_languages]
    alt_matched = [lang for lang in candidate.alternative_languages if lang in detected_languages]

    if primary_matched:
        language_score = 35.0
        matched_languages.extend(primary_matched)
    elif alt_matched:
        # Role mentions acceptable alternate language (e.g., Go or Java)
        language_score = 25.0
        matched_languages.extend(alt_matched)
    elif not detected_languages:
        # Language not explicitly specified in text, neutral partial score
        language_score = 15.0
    else:
        # Specific languages mentioned, but neither candidate's primary nor alternatives
        language_score = 0.0

    # 5. Required and Preferred Skills Matching (up to 30 pts)
    matched_skills = []
    missing_skills = []
    
    # Required skills (15 pts)
    req_hits = 0
    for req in candidate.required_skills:
        if req in job.extracted_skills or re.search(rf"\b{re.escape(req)}\b", job_full_text, re.IGNORECASE):
            req_hits += 1
            matched_skills.append(req)
        else:
            missing_skills.append(req)

    req_score = (req_hits / len(candidate.required_skills) * 15.0) if candidate.required_skills else 15.0

    # Preferred skills (15 pts)
    pref_hits = 0
    for pref in candidate.preferred_skills:
        if pref in job.extracted_skills or re.search(rf"\b{re.escape(pref)}\b", job_full_text, re.IGNORECASE):
            pref_hits += 1
            matched_skills.append(pref)

    pref_score = (pref_hits / len(candidate.preferred_skills) * 15.0) if candidate.preferred_skills else 15.0

    skills_score = req_score + pref_score

    # Compute Total Score
    total_score = round(title_score + language_score + skills_score, 1)

    # Determine Recommendation
    # High score & eligible -> MATCH
    # Medium score or needs verification -> REVIEW
    # Ineligible or low score -> EXCLUDE / REVIEW
    if eligibility_status == eligibility_status.INELIGIBLE:
        recommendation = Recommendation.EXCLUDE
    elif total_score >= 65.0 and eligibility_status == eligibility_status.ELIGIBLE:
        recommendation = Recommendation.MATCH
    elif total_score >= 45.0 or eligibility_status == eligibility_status.NEEDS_VERIFICATION:
        recommendation = Recommendation.REVIEW
    else:
        recommendation = Recommendation.EXCLUDE

    # Generate Human-Readable Explanation
    parts = []
    if matched_languages:
        parts.append(f"Tech stack matches: {', '.join(matched_languages)}")
    elif detected_languages:
        parts.append(f"Requires different languages ({', '.join(detected_languages)})")
    if matched_skills:
        parts.append(f"Matched skills: {', '.join(matched_skills[:4])}")
    if missing_skills:
        parts.append(f"Missing: {', '.join(missing_skills)}")
    parts.append(f"Location status: {eligibility_status.value} ({eligibility_reason})")

    explanation = "; ".join(parts)

    return CandidateMatchResult(
        candidate_id=candidate.id,
        job_id=job.id,
        relevance_score=total_score,
        recommendation=recommendation,
        eligibility_status=eligibility_status,
        eligibility_reason=eligibility_reason,
        matched_titles=matched_titles,
        matched_languages=matched_languages,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        exclusion_reasons=exclusion_reasons,
        explanation=explanation,
    )
