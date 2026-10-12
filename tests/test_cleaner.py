from src.analyzer.cleaner import unescape_and_clean_html


def test_html_unescape_and_clean():
    raw_html = "&lt;div class=&quot;intro&quot;&gt;&lt;p&gt;Hello World!&lt;/p&gt;&lt;br/&gt;&lt;p&gt;Second Line&lt;/p&gt;&lt;/div&gt;"
    decoded, clean_text, fingerprint = unescape_and_clean_html(raw_html)

    assert "<div" in decoded
    assert "&lt;" not in decoded
    assert "Hello World!" in clean_text
    assert "Second Line" in clean_text
    assert "<p>" not in clean_text
    assert len(fingerprint) == 64  # SHA-256


def test_fingerprint_idempotency_and_sensitivity():
    html_1 = "&lt;p&gt;Python Engineer at TechCorp&lt;/p&gt;"
    html_2 = "<p>Python Engineer at TechCorp</p>"
    html_3 = "<p>Python Engineer at OtherCorp</p>"

    _, _, fp_1 = unescape_and_clean_html(html_1)
    _, _, fp_2 = unescape_and_clean_html(html_2)
    _, _, fp_3 = unescape_and_clean_html(html_3)

    # Identical underlying text should yield identical SHA-256
    assert fp_1 == fp_2
    # Different text should yield different SHA-256
    assert fp_1 != fp_3


def test_empty_html_handling():
    decoded, clean_text, fingerprint = unescape_and_clean_html("")
    assert decoded == ""
    assert clean_text == ""
    assert len(fingerprint) == 64
