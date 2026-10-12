import re
from typing import Tuple, Optional
from .schemas import ATSProvider

GREENHOUSE_PATTERNS = [
    (re.compile(r"greenhouse\.io/embed/job_board\.js\?for=([a-zA-Z0-9_-]+)", re.IGNORECASE), "Greenhouse script embed"),
    (re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-zA-Z0-9_-]+)", re.IGNORECASE), "Greenhouse board link/iframe"),
    (re.compile(r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)", re.IGNORECASE), "Greenhouse API reference"),
]

LEVER_PATTERNS = [
    (re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.IGNORECASE), "Lever hosted career page"),
]

ASHBY_PATTERNS = [
    (re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE), "Ashby hosted career page"),
]

WORKDAY_PATTERNS = [
    (re.compile(r"([a-zA-Z0-9_-]+)\.wd\d+\.myworkdayjobs\.com", re.IGNORECASE), "Workday jobs portal"),
]


def detect_ats_signature(url: str, html_content: str) -> Tuple[ATSProvider, Optional[str], str]:
    """
    Scans URL and page HTML for ATS signatures.
    Returns: (ATSProvider, board_identifier, evidence)
    """
    search_context = f"{url}\n{html_content}"

    # 1. Check Greenhouse signatures
    for pattern, description in GREENHOUSE_PATTERNS:
        match = pattern.search(search_context)
        if match:
            slug = match.group(1).strip()
            # Exclude false positives like 'embed' or 'js'
            if slug.lower() not in ("embed", "js", "v1", "api"):
                return ATSProvider.GREENHOUSE, slug, f"{description}: '{match.group(0)}'"

    # 2. Check Lever signatures
    for pattern, description in LEVER_PATTERNS:
        match = pattern.search(search_context)
        if match:
            slug = match.group(1).strip()
            return ATSProvider.LEVER, slug, f"{description}: '{match.group(0)}'"

    # 3. Check Ashby signatures
    for pattern, description in ASHBY_PATTERNS:
        match = pattern.search(search_context)
        if match:
            slug = match.group(1).strip()
            return ATSProvider.ASHBY, slug, f"{description}: '{match.group(0)}'"

    # 4. Check Workday signatures
    for pattern, description in WORKDAY_PATTERNS:
        match = pattern.search(search_context)
        if match:
            slug = match.group(1).strip()
            return ATSProvider.WORKDAY, slug, f"{description}: '{match.group(0)}'"

    return ATSProvider.UNKNOWN, None, "No recognized ATS signature detected in page content."
