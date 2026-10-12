from typing import Tuple, Optional
import httpx
from .ssrf import validate_safe_url

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB limit
MAX_REDIRECTS = 5


class SafeCrawler:
    """
    Crawls career URLs safely with SSRF pre-checks, redirect validation, and size capping.
    """
    def __init__(self, timeout: float = 10.0, user_agent: str = "RolePilot-Inspector/1.0"):
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def fetch_page(
        self,
        url: str,
        client: Optional[httpx.AsyncClient] = None
    ) -> Tuple[str, int, str]:
        """
        Safely fetches page HTML.
        Returns: (final_url, status_code, html_content)
        """
        current_url = validate_safe_url(url)
        redirect_count = 0

        should_close = False
        if client is None:
            client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=False,
            )
            should_close = True

        try:
            while redirect_count <= MAX_REDIRECTS:
                response = await client.get(current_url)

                # Check for HTTP redirects
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        break
                    # Resolve relative redirect if needed
                    next_url = str(response.url.join(location))
                    current_url = validate_safe_url(next_url)
                    redirect_count += 1
                    continue

                # Stream and cap body size
                content_bytes = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    content_bytes.extend(chunk)
                    if len(content_bytes) > MAX_BODY_BYTES:
                        break

                text = content_bytes.decode("utf-8", errors="replace")
                return str(response.url), response.status_code, text

            raise ValueError(f"Exceeded maximum redirect limit of {MAX_REDIRECTS} hops.")
        finally:
            if should_close:
                await client.aclose()
