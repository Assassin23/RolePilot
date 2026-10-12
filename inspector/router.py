import asyncio
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from .schemas import (
    InspectionRequest,
    InspectionResponse,
    InspectionStatus,
    ATSProvider,
    BatchCatalogRequest,
    BatchCatalogResponse,
)
from .catalog import TARGET_100_TECH_COMPANIES
from .crawler import SafeCrawler
from .detector import detect_ats_signature
from .probers.greenhouse import probe_greenhouse_board

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Inspection"])


async def _inspect_company(
    company_name: str,
    careers_url: str,
    slug_hint: Optional[str] = None,
    crawler: Optional[SafeCrawler] = None,
) -> InspectionResponse:
    if crawler is None:
        crawler = SafeCrawler()

    # Step 1: Safely crawl the page
    html_text = ""
    final_url = careers_url
    crawl_error = None
    try:
        final_url, status_code, html_text = await crawler.fetch_page(careers_url)
    except ValueError as e:
        crawl_error = f"Security / validation error: {str(e)}"
    except Exception as e:
        crawl_error = f"Network error accessing career URL: {str(e)}"

    # Step 2: Detect ATS signature from HTML
    ats, slug, detector_evidence = ATSProvider.UNKNOWN, None, crawl_error or "No ATS detected in HTML"
    if html_text:
        ats, slug, detector_evidence = detect_ats_signature(final_url, html_text)

    # Step 3: Handle Greenhouse boards via API live prober
    target_slug = slug or slug_hint
    if ats == ATSProvider.GREENHOUSE or (target_slug and ats == ATSProvider.UNKNOWN):
        if target_slug:
            is_accessible, jobs_count, api_endpoint, probe_evidence = await probe_greenhouse_board(target_slug)
            if is_accessible:
                return InspectionResponse(
                    status=InspectionStatus.VERIFIED,
                    company_name=company_name,
                    careers_url=careers_url,
                    detected_ats=ATSProvider.GREENHOUSE,
                    board_identifier=target_slug,
                    api_endpoint=api_endpoint,
                    is_api_accessible=True,
                    published_jobs_count=jobs_count,
                    confidence="HIGH",
                    evidence=f"{detector_evidence}; {probe_evidence}",
                )
            elif ats == ATSProvider.GREENHOUSE:
                return InspectionResponse(
                    status=InspectionStatus.NOT_FOUND,
                    company_name=company_name,
                    careers_url=careers_url,
                    detected_ats=ATSProvider.GREENHOUSE,
                    board_identifier=target_slug,
                    api_endpoint=api_endpoint,
                    is_api_accessible=False,
                    confidence="LOW",
                    evidence=f"{detector_evidence}; Probe failed: {probe_evidence}",
                )

    # Step 4: Handle identified other ATS systems (outside MVP scope)
    if ats in (ATSProvider.LEVER, ATSProvider.ASHBY, ATSProvider.WORKDAY):
        return InspectionResponse(
            status=InspectionStatus.UNSUPPORTED_ATS,
            company_name=company_name,
            careers_url=careers_url,
            detected_ats=ats,
            board_identifier=slug,
            confidence="HIGH",
            evidence=f"{detector_evidence}. This ATS provider is identified but outside Greenhouse MVP scope.",
        )

    # Step 5: If there was a crawl error and no probe succeeded
    if crawl_error:
        return InspectionResponse(
            status=InspectionStatus.ERROR,
            company_name=company_name,
            careers_url=careers_url,
            detected_ats=ATSProvider.UNKNOWN,
            evidence=crawl_error,
        )

    # Step 6: No ATS detected
    return InspectionResponse(
        status=InspectionStatus.NOT_FOUND,
        company_name=company_name,
        careers_url=careers_url,
        detected_ats=ATSProvider.UNKNOWN,
        confidence="NONE",
        evidence=detector_evidence,
    )


@router.post("/inspect", response_model=InspectionResponse)
async def inspect_career_page(req: InspectionRequest) -> InspectionResponse:
    """
    Inspects a company career page URL, extracts ATS signatures,
    probes the provider API, and returns a verified status report.
    """
    return await _inspect_company(
        company_name=req.company_name,
        careers_url=req.careers_url,
        slug_hint=req.slug_hint,
    )


@router.get("/catalog", response_model=List[dict])
async def get_tech_companies_catalog():
    """
    Returns the curated catalog of 100 target technology, AI, cloud,
    and developer-tool companies.
    """
    return TARGET_100_TECH_COMPANIES


@router.post("/catalog/verify", response_model=BatchCatalogResponse)
async def verify_catalog(req: Optional[BatchCatalogRequest] = None) -> BatchCatalogResponse:
    """
    Iterates through the curated tech companies catalog, crawls their career pages,
    detects their ATS, probes Greenhouse APIs, and returns verified active boards.
    """
    if req is None:
        req = BatchCatalogRequest()

    companies = TARGET_100_TECH_COMPANIES
    if req.limit and req.limit > 0:
        companies = companies[:req.limit]

    concurrency = max(1, min(req.concurrency, 10))
    semaphore = asyncio.Semaphore(concurrency)
    crawler = SafeCrawler()

    async def _worker(item: dict) -> InspectionResponse:
        async with semaphore:
            return await _inspect_company(
                company_name=item["name"],
                careers_url=item["careers_url"],
                slug_hint=item.get("slug_hint"),
                crawler=crawler,
            )

    tasks = [_worker(comp) for comp in companies]
    results: List[InspectionResponse] = await asyncio.gather(*tasks)

    verified_boards = []
    v_count = 0
    u_count = 0
    nf_count = 0
    err_count = 0

    for r in results:
        if r.status == InspectionStatus.VERIFIED:
            v_count += 1
            verified_boards.append({
                "company_name": r.company_name,
                "token": r.board_identifier,
                "api_endpoint": r.api_endpoint,
                "published_jobs_count": r.published_jobs_count,
                "careers_url": r.careers_url,
            })
        elif r.status == InspectionStatus.UNSUPPORTED_ATS:
            u_count += 1
        elif r.status == InspectionStatus.NOT_FOUND:
            nf_count += 1
        else:
            err_count += 1

    return BatchCatalogResponse(
        total_inspected=len(results),
        verified_greenhouse_count=v_count,
        unsupported_ats_count=u_count,
        not_found_count=nf_count,
        error_count=err_count,
        verified_greenhouse_boards=verified_boards,
        results=results,
    )

