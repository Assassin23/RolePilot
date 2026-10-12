import re
from typing import Tuple, List
from src.schemas.job import CanonicalJob, WorkMode
from src.schemas.candidate import CandidateProfile, EligibilityStatus

# Common country tokens and regional groups
APAC_COUNTRIES = {"IN", "JP", "SG", "AU", "NZ", "KR", "VN", "ID", "MY", "PH", "TH"}
EMEA_COUNTRIES = {"GB", "DE", "FR", "NL", "ES", "IT", "SE", "PL", "IE", "ZA", "AE"}
NORTH_AMERICA_COUNTRIES = {"US", "CA", "MX"}

COUNTRY_ALIASES = {
    "IN": [r"\bindia\b", r"\bindian\b", r"\bbengaluru\b", r"\bbangalore\b", r"\bdehradun\b", r"\bdelhi\b", r"\bmumbai\b", r"\bpune\b", r"\bhyderabad\b"],
    "US": [r"\bu\.?s\.?a?\b", r"\bunited\s+states\b", r"\bamerica\b", r"\bnyc\b", r"\bsan\s+francisco\b", r"\bcalifornia\b"],
    "GB": [r"\buk\b", r"\bunited\s+kingdom\b", r"\blondon\b", r"\bengland\b"],
    "DE": [r"\bgermany\b", r"\bberlin\b", r"\bmunich\b"],
}

COUNTRY_NAMES = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "DE": "Germany",
    "CA": "Canada",
}

# Explicit geographic exclusion patterns
US_ONLY_PATTERNS = [
    re.compile(r"\b(?:u\.?s\.?a?|united\s+states)\s+only\b", re.IGNORECASE),
    re.compile(r"\b(?:must|eligible\s+to)\s+work\s+in\s+the\s+u\.?s\.?\b", re.IGNORECASE),
    re.compile(r"\bnorth\s+america\s+only\b", re.IGNORECASE),
    re.compile(r"\bus\s+citizens?\s+only\b", re.IGNORECASE),
]

WORLDWIDE_PATTERNS = [
    re.compile(r"\bwork\s+from\s+anywhere\b", re.IGNORECASE),
    re.compile(r"\bworldwide\b", re.IGNORECASE),
    re.compile(r"\banywhere\s+in\s+the\s+world\b", re.IGNORECASE),
    re.compile(r"\bglobal\s+remote\b", re.IGNORECASE),
    re.compile(r"\bany\s+location\b", re.IGNORECASE),
]


def evaluate_location_eligibility(
    job: CanonicalJob,
    candidate: CandidateProfile,
) -> Tuple[EligibilityStatus, str]:
    """
    Evaluates whether a job is location-compatible with the candidate.
    Returns (EligibilityStatus, explanation_reason).
    """
    home_country = candidate.home_country.upper().strip()
    home_city = candidate.home_city.lower().strip() if candidate.home_city else None

    locations_text = " ".join(job.listed_locations).lower()
    full_context = f"{job.title} | {locations_text} | {job.description_clean_text[:1500].lower()}"

    # Helper: Does text match candidate country?
    country_regexes = COUNTRY_ALIASES.get(home_country, [re.escape(home_country.lower())])
    matches_home_country = any(re.search(pat, full_context, re.IGNORECASE) for pat in country_regexes)

    # 1. On-site and Hybrid roles
    if job.work_mode in (WorkMode.ONSITE, WorkMode.HYBRID):
        if not matches_home_country:
            return (
                EligibilityStatus.INELIGIBLE,
                f"{job.work_mode.value} position located outside home country ({candidate.home_country})."
            )
        
        # In home country: check city if candidate has specified one
        if home_city:
            if home_city in locations_text or home_city in full_context:
                return (
                    EligibilityStatus.ELIGIBLE,
                    f"Compatible {job.work_mode.value} position in candidate's home city ({candidate.home_city}, {candidate.home_country})."
                )
            else:
                return (
                    EligibilityStatus.NEEDS_VERIFICATION,
                    f"{job.work_mode.value} position in {candidate.home_country}, but specific city attendance required (candidate in {candidate.home_city})."
                )
        return (
            EligibilityStatus.ELIGIBLE,
            f"{job.work_mode.value} position located in candidate's country ({candidate.home_country})."
        )

    # 2. Remote roles
    if job.work_mode == WorkMode.REMOTE:
        # Check negative restrictions (e.g. US Only)
        if home_country != "US":
            for pat in US_ONLY_PATTERNS:
                if pat.search(full_context):
                    return (
                        EligibilityStatus.INELIGIBLE,
                        f"Remote position is restricted to US/North America candidates ('{pat.pattern}')."
                    )

        # Check explicit home country allowance
        if matches_home_country:
            country_display = COUNTRY_NAMES.get(home_country, candidate.home_country)
            return (
                EligibilityStatus.ELIGIBLE,
                f"Remote position explicitly available in candidate's home country ({country_display} / {candidate.home_country})."
            )

        # Check worldwide / anywhere remote
        for pat in WORLDWIDE_PATTERNS:
            if pat.search(full_context):
                return (
                    EligibilityStatus.ELIGIBLE,
                    "Remote position permits work from anywhere worldwide."
                )

        # Check regional coverage (e.g., APAC)
        if "apac" in full_context and home_country in APAC_COUNTRIES:
            return (
                EligibilityStatus.ELIGIBLE,
                f"Regional APAC remote posting covers candidate's country ({candidate.home_country})."
            )
        if "emea" in full_context and home_country in EMEA_COUNTRIES:
            return (
                EligibilityStatus.ELIGIBLE,
                f"Regional EMEA remote posting covers candidate's country ({candidate.home_country})."
            )

        # If listing only mentions other foreign countries (e.g. "Remote, UK", "Remote, Germany")
        if any(re.search(pat, locations_text, re.IGNORECASE) for code, pats in COUNTRY_ALIASES.items() if code != home_country for pat in pats):
            return (
                EligibilityStatus.INELIGIBLE,
                f"Remote position restricted to locations other than candidate country ({candidate.home_country})."
            )

        # Generic "Remote" with no geographic boundaries stated
        return (
            EligibilityStatus.NEEDS_VERIFICATION,
            "Listing states 'Remote' without specified geographic or payroll bounds; requires employer verification."
        )

    # 3. Work mode is UNKNOWN
    if matches_home_country:
        return (
            EligibilityStatus.NEEDS_VERIFICATION,
            f"Mentions {candidate.home_country}, but work mode (on-site/remote) is undetermined."
        )

    return (
        EligibilityStatus.NEEDS_VERIFICATION,
        "Undetermined work mode and geographic eligibility."
    )
