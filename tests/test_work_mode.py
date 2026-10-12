from src.analyzer.work_mode import classify_work_mode
from src.schemas.job import WorkMode


def test_classify_remote_from_title():
    mode, evidence = classify_work_mode(
        title="Senior Python Engineer (Remote)",
        listed_locations=["San Francisco, CA"],
        description_text="We build web APIs."
    )
    assert mode == WorkMode.REMOTE
    assert "Remote" in evidence


def test_classify_remote_from_location():
    mode, evidence = classify_work_mode(
        title="Backend Developer",
        listed_locations=["Remote, India"],
        description_text="Work with our team."
    )
    assert mode == WorkMode.REMOTE
    assert "Remote, India" in evidence


def test_classify_hybrid():
    mode, evidence = classify_work_mode(
        title="Software Engineer",
        listed_locations=["London, UK"],
        description_text="We have a hybrid schedule with 3 days in the office required."
    )
    assert mode == WorkMode.HYBRID
    assert "hybrid" in evidence.lower() or "office" in evidence.lower()


def test_classify_onsite():
    mode, evidence = classify_work_mode(
        title="Python Developer",
        listed_locations=["Bengaluru, India"],
        description_text="Full-time on-site role in our Bengaluru headquarters."
    )
    assert mode == WorkMode.ONSITE
    assert "on-site" in evidence.lower() or "locations" in evidence.lower()
