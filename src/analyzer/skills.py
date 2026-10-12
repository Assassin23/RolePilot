import re
from typing import List, Tuple

SKILL_VOCABULARY = {
    "Python": [r"\bpython\b"],
    "FastAPI": [r"\bfastapi\b"],
    "Django": [r"\bdjango\b"],
    "Flask": [r"\bflask\b"],
    "PostgreSQL": [r"\bpostgres(?:ql)?\b"],
    "MySQL": [r"\bmysql\b"],
    "Redis": [r"\bredis\b"],
    "MongoDB": [r"\bmongo(?:db)?\b"],
    "SQLAlchemy": [r"\bsqlalchemy\b"],
    "REST API": [r"\brest(?:ful)?(?:\s+api)?\b", r"\brest\s+apis?\b"],
    "GraphQL": [r"\bgraphql\b"],
    "gRPC": [r"\bgrpc\b"],
    "Docker": [r"\bdocker\b"],
    "Kubernetes": [r"\b(?:kubernetes|k8s)\b"],
    "AWS": [r"\baws\b", r"\bamazon\s+web\s+services\b"],
    "GCP": [r"\bgcp\b", r"\bgoogle\s+cloud\b"],
    "Azure": [r"\bazure\b"],
    "CI/CD": [r"\bci[/-]cd\b"],
    "Celery": [r"\bcelery\b"],
    "Kafka": [r"\bkafka\b"],
    "RabbitMQ": [r"\brabbitmq\b"],
    "Pytest": [r"\bpytest\b"],
    "Git": [r"\bgit\b"],
}

SENIORITY_PATTERNS = [
    ("INTERN", [r"\bintern(?:ship)?\b", r"\btrainee\b"]),
    ("JUNIOR", [r"\bjunior\b", r"\bjr\.?\b", r"\bentry[- ]level\b", r"\bassociate\b"]),
    ("STAFF", [r"\bstaff\b", r"\bprincipal\b", r"\barchitect\b"]),
    ("LEAD", [r"\blead\b", r"\btech\s+lead\b", r"\bengineering\s+lead\b"]),
    ("SENIOR", [r"\bsenior\b", r"\bsr\.?\b"]),
    ("MID", [r"\bintermediate\b", r"\bmid[- ]level\b", r"\b3\s*[-+]\s*5\s*years\b"]),
]


def extract_skills_and_seniority(title: str, text: str) -> Tuple[List[str], str]:
    """
    Extracts technology skills and detected seniority level from job posting.
    Returns (extracted_skills, seniority_level).
    """
    full_text = f"{title}\n{text}"
    extracted_skills: List[str] = []

    for skill, patterns in SKILL_VOCABULARY.items():
        for pattern in patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                extracted_skills.append(skill)
                break

    # Determine seniority (check title first, then body)
    for level, patterns in SENIORITY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, title, re.IGNORECASE):
                return sorted(extracted_skills), level

    for level, patterns in SENIORITY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text[:1500], re.IGNORECASE):
                return sorted(extracted_skills), level

    return sorted(extracted_skills), "MID"  # Default assumption for unmarked professional roles
