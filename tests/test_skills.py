from src.analyzer.skills import extract_skills_and_seniority


def test_extract_python_backend_skills():
    title = "Backend Engineer"
    text = (
        "We are looking for an engineer with strong Python and FastAPI experience. "
        "Must be proficient with PostgreSQL, Redis caching, Docker containers, and CI/CD pipelines. "
        "Experience with REST APIs and Pytest is required."
    )
    skills, seniority = extract_skills_and_seniority(title, text)

    assert "Python" in skills
    assert "FastAPI" in skills
    assert "PostgreSQL" in skills
    assert "Redis" in skills
    assert "Docker" in skills
    assert "REST API" in skills
    assert "Pytest" in skills
    assert "CI/CD" in skills
    assert seniority == "MID"


def test_seniority_detection():
    # Senior
    _, s1 = extract_skills_and_seniority("Senior Python Developer", "Python backend")
    assert s1 == "SENIOR"

    # Junior
    _, s2 = extract_skills_and_seniority("Junior Software Engineer", "Python backend")
    assert s2 == "JUNIOR"

    # Staff / Principal
    _, s3 = extract_skills_and_seniority("Staff Backend Engineer", "Distributed systems")
    assert s3 == "STAFF"

    # Intern
    _, s4 = extract_skills_and_seniority("Software Engineering Intern", "Python")
    assert s4 == "INTERN"
