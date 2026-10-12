import html
import hashlib
import re
from typing import Tuple


def unescape_and_clean_html(raw_html: str) -> Tuple[str, str, str]:
    """
    Cleans raw HTML from job postings.
    Returns:
        (decoded_html, clean_text, content_fingerprint)
    """
    if not raw_html:
        empty_hash = hashlib.sha256("".encode("utf-8")).hexdigest()
        return "", "", empty_hash

    # Step 1: Unescape HTML entities (e.g. &lt;p&gt; -> <p>)
    decoded_html = html.unescape(raw_html)

    # Step 2: Convert block-level elements & breaks to newlines before stripping
    text = re.sub(r"<(?:br|p|div|li|h[1-6]|tr)[^>]*>", "\n", decoded_html, flags=re.IGNORECASE)
    
    # Step 3: Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    
    # Step 4: Unescape any nested entities
    text = html.unescape(text)

    # Step 5: Normalize spaces and consecutive newlines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    clean_text = "\n".join(line for line in lines if line)

    # Step 6: Compute deterministic SHA-256 fingerprint on normalized lowercase text
    normalized_for_hash = re.sub(r"\s+", " ", clean_text.lower()).strip()
    fingerprint = hashlib.sha256(normalized_for_hash.encode("utf-8")).hexdigest()

    return decoded_html, clean_text, fingerprint
