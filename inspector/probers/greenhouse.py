from typing import Tuple, Optional
import httpx


async def probe_greenhouse_board(
    board_slug: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 10.0
) -> Tuple[bool, int, str, str]:
    """
    Probes the public Greenhouse Job Board API to verify validity and job counts.
    Returns: (is_accessible, jobs_count, api_endpoint, evidence)
    """
    clean_slug = board_slug.strip().lower()
    endpoint = f"https://boards-api.greenhouse.io/v1/boards/{clean_slug}/jobs"

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "RolePilot-Inspector/1.0"})
        should_close = True

    try:
        response = await client.get(endpoint)
        if response.status_code == 200:
            data = response.json()
            jobs = data.get("jobs", [])
            total = data.get("meta", {}).get("total", len(jobs))
            return True, total, endpoint, f"HTTP 200 OK — {total} published jobs active."
        elif response.status_code == 404:
            return False, 0, endpoint, f"HTTP 404 Not Found — Board identifier '{clean_slug}' does not exist."
        elif response.status_code == 403:
            return False, 0, endpoint, "HTTP 403 Forbidden — Board is private or requires Harvest API key."
        else:
            return False, 0, endpoint, f"HTTP {response.status_code} — Unexpected response from Greenhouse API."
    except Exception as e:
        return False, 0, endpoint, f"Probe connection error: {str(e)}"
    finally:
        if should_close:
            await client.aclose()
