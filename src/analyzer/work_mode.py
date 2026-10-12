import re
from typing import List, Tuple
from src.schemas.job import WorkMode


HYBRID_PATTERNS = [
    re.compile(r"\bhybrid\b", re.IGNORECASE),
    re.compile(r"\b(?:2|3|4)\s*days\s*(?:in|from)\s*(?:the\s*)?office\b", re.IGNORECASE),
    re.compile(r"\boffice\s+and\s+remote\b", re.IGNORECASE),
    re.compile(r"\bpartial\s+remote\b", re.IGNORECASE),
]

REMOTE_PATTERNS = [
    re.compile(r"\ball[- ]remote\b", re.IGNORECASE),
    re.compile(r"\bfully\s+remote\b", re.IGNORECASE),
    re.compile(r"\b100%\s+remote\b", re.IGNORECASE),
    re.compile(r"\bremote[- ]first\b", re.IGNORECASE),
    re.compile(r"\bwork\s+from\s+anywhere\b", re.IGNORECASE),
    re.compile(r"\bvirtual\s+role\b", re.IGNORECASE),
    re.compile(r"\bremote\b", re.IGNORECASE),
    re.compile(r"\bwork\s+from\s+home\b", re.IGNORECASE),
]

ONSITE_PATTERNS = [
    re.compile(r"\bon[- ]site\b", re.IGNORECASE),
    re.compile(r"\bin[- ]person\b", re.IGNORECASE),
    re.compile(r"\boffice[- ]based\b", re.IGNORECASE),
    re.compile(r"\bmust\s+be\s+located\s+in\s+our\s+office\b", re.IGNORECASE),
]


def classify_work_mode(
    title: str,
    listed_locations: List[str],
    description_text: str
) -> Tuple[WorkMode, str]:
    """
    Classifies the work mode of a job into REMOTE, HYBRID, ONSITE, or UNKNOWN.
    Returns (WorkMode, evidence_snippet).
    """
    locations_joined = " | ".join(listed_locations)
    header_context = f"{title} | {locations_joined}"

    # 1. Check title & location fields first (highest priority context)
    for pattern in HYBRID_PATTERNS:
        match = pattern.search(header_context)
        if match:
            return WorkMode.HYBRID, f"Header match: '{match.group(0)}' in '{header_context}'"

    for pattern in REMOTE_PATTERNS:
        match = pattern.search(header_context)
        if match:
            return WorkMode.REMOTE, f"Header match: '{match.group(0)}' in '{header_context}'"

    for pattern in ONSITE_PATTERNS:
        match = pattern.search(header_context)
        if match:
            return WorkMode.ONSITE, f"Header match: '{match.group(0)}' in '{header_context}'"

    # 2. Check the job description body
    # Hybrid check has precedence over general 'remote' mentions in text
    for pattern in HYBRID_PATTERNS:
        match = pattern.search(description_text[:2000])  # prioritize top sections
        if match:
            start = max(0, match.start() - 30)
            end = min(len(description_text), match.end() + 30)
            snippet = description_text[start:end].replace("\n", " ").strip()
            return WorkMode.HYBRID, f"Description snippet: '...{snippet}...'"

    for pattern in REMOTE_PATTERNS:
        match = pattern.search(description_text[:2000])
        if match:
            start = max(0, match.start() - 30)
            end = min(len(description_text), match.end() + 30)
            snippet = description_text[start:end].replace("\n", " ").strip()
            return WorkMode.REMOTE, f"Description snippet: '...{snippet}...'"

    for pattern in ONSITE_PATTERNS:
        match = pattern.search(description_text[:2000])
        if match:
            start = max(0, match.start() - 30)
            end = min(len(description_text), match.end() + 30)
            snippet = description_text[start:end].replace("\n", " ").strip()
            return WorkMode.ONSITE, f"Description snippet: '...{snippet}...'"

    # 3. If explicit physical locations are present without any remote signals
    if listed_locations and not any("remote" in loc.lower() for loc in listed_locations):
        return WorkMode.ONSITE, f"Physical locations listed with no remote indicators: {locations_joined}"

    return WorkMode.UNKNOWN, "Insufficient signals in title, locations, or description"
