import asyncio
from urllib.parse import urlparse
import yaml
from pathlib import Path
from django.core.management.base import BaseCommand
import httpx

from inspector.catalog import TARGET_100_TECH_COMPANIES
from inspector.crawler import SafeCrawler
from inspector.detector import detect_ats_signature, ATSProvider
from inspector.probers.greenhouse import probe_greenhouse_board
from inspector.router import _inspect_company, InspectionStatus


class Command(BaseCommand):
    help = "Inspects company career pages, detects ATS signatures, probes public APIs, and registers verified boards."

    def add_arguments(self, parser):
        parser.add_argument("url", nargs="?", type=str, default="", help="Official careers page URL to inspect")
        parser.add_argument("--name", type=str, default="", help="Company name (optional)")
        parser.add_argument("--catalog", action="store_true", help="Inspect the curated 100 tech companies catalog in batch")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to inspect from catalog")
        parser.add_argument("--concurrency", type=int, default=5, help="Concurrent workers for catalog inspection (default 5)")
        parser.add_argument("--register", action="store_true", help="Automatically register verified Greenhouse boards into config/boards.yaml")

    def handle(self, *args, **options):
        is_catalog = options["catalog"]
        url = options["url"].strip()
        auto_register = options["register"]

        if is_catalog:
            self._handle_catalog(options["limit"], options["concurrency"], auto_register)
        elif url:
            self._handle_single(url, options["name"], auto_register)
        else:
            self.stdout.write(self.style.ERROR("Please provide a career page URL or use --catalog to inspect the 100-company catalog."))

    def _handle_catalog(self, limit, concurrency, auto_register):
        companies = TARGET_100_TECH_COMPANIES
        if limit and limit > 0:
            companies = companies[:limit]

        self.stdout.write(self.style.NOTICE("=" * 80))
        self.stdout.write(self.style.NOTICE(f" BATCH INSPECTING {len(companies)} TARGET TECH COMPANIES (Concurrency: {concurrency})"))
        self.stdout.write(self.style.NOTICE("=" * 80))

        async def _run_batch():
            sem = asyncio.Semaphore(max(1, min(concurrency, 10)))
            crawler = SafeCrawler()

            async def _worker(item):
                async with sem:
                    return await _inspect_company(
                        company_name=item["name"],
                        careers_url=item["careers_url"],
                        slug_hint=item.get("slug_hint"),
                        crawler=crawler,
                    )

            tasks = [_worker(c) for c in companies]
            return await asyncio.gather(*tasks)

        results = asyncio.run(_run_batch())

        verified = []
        unsupported = []
        not_found = []

        for r in results:
            if r.status == InspectionStatus.VERIFIED:
                verified.append(r)
                self.stdout.write(self.style.SUCCESS(f"  [VERIFIED] {r.company_name:<20} -> Greenhouse slug: '{r.board_identifier}' ({r.published_jobs_count} live jobs)"))
            elif r.status == InspectionStatus.UNSUPPORTED_ATS:
                unsupported.append(r)
                self.stdout.write(self.style.WARNING(f"  [ATS FOUND] {r.company_name:<20} -> {r.detected_ats.value.upper()}"))
            else:
                not_found.append(r)

        self.stdout.write(self.style.NOTICE("\n" + "=" * 80))
        self.stdout.write(self.style.NOTICE(f" SUMMARY: Total={len(results)} | Verified Greenhouse={len(verified)} | Other ATS={len(unsupported)} | Not Found={len(not_found)}"))
        self.stdout.write(self.style.NOTICE("=" * 80))

        if auto_register and verified:
            config_path = Path("config/boards.yaml")
            data = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}

            boards = data.get("boards", [])
            existing_slugs = {b["token"] for b in boards}
            new_added = 0

            for v in verified:
                if v.board_identifier not in existing_slugs:
                    boards.append({
                        "token": v.board_identifier,
                        "company_name": v.company_name,
                        "enabled": True,
                        "notes": f"Verified via 100-company catalog inspector ({v.published_jobs_count} active jobs)"
                    })
                    existing_slugs.add(v.board_identifier)
                    new_added += 1

            data["boards"] = boards
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, sort_keys=False)

            self.stdout.write(self.style.SUCCESS(f" Successfully registered {new_added} new active Greenhouse boards in config/boards.yaml!"))

    def _handle_single(self, url, name, auto_register):
        name = name or urlparse(url).netloc.split(".")[1].capitalize()

        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE(f" INSPECTING CAREER PAGE: {url}"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        crawler = SafeCrawler()
        try:
            final_url, status_code, html_text = asyncio.run(crawler.fetch_page(url))
            self.stdout.write(f"Target fetched successfully: HTTP {status_code} (Final URL: {final_url})")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Crawler / Security failure: {str(e)}"))
            return

        ats, slug, detector_evidence = detect_ats_signature(final_url, html_text)
        self.stdout.write(f"Detected ATS: {ats.value.upper()}")
        self.stdout.write(f"Evidence: {detector_evidence}")

        if ats == ATSProvider.GREENHOUSE and slug:
            self.stdout.write(f"Probing Greenhouse Board Token: '{slug}'...")
            is_ok, count, endpoint, probe_evidence = asyncio.run(probe_greenhouse_board(slug))
            if is_ok:
                self.stdout.write(self.style.SUCCESS(f"VERIFIED ACTIVE BOARD: '{slug}' ({count} published jobs)"))
                self.stdout.write(f"API Endpoint: {endpoint}")

                if auto_register:
                    config_path = Path("config/boards.yaml")
                    data = {}
                    if config_path.exists():
                        with open(config_path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}

                    boards = data.get("boards", [])
                    existing = [b["token"] for b in boards]
                    if slug not in existing:
                        boards.append({
                            "token": slug,
                            "company_name": name,
                            "enabled": True,
                            "notes": f"Auto-verified via career inspection of {url}"
                        })
                        data["boards"] = boards
                        with open(config_path, "w", encoding="utf-8") as f:
                            yaml.dump(data, f, sort_keys=False)
                        self.stdout.write(self.style.SUCCESS(f"Registered '{slug}' in config/boards.yaml"))
                    else:
                        self.stdout.write(self.style.WARNING(f"Board '{slug}' already exists in config/boards.yaml"))
            else:
                self.stdout.write(self.style.WARNING(f"Board probe failed: {probe_evidence}"))
        elif ats != ATSProvider.UNKNOWN:
            self.stdout.write(self.style.WARNING(f"ATS '{ats.value.upper()}' identified, but outside Greenhouse MVP scope."))
        else:
            self.stdout.write(self.style.ERROR("No recognized ATS detected on this career page."))

        self.stdout.write(self.style.NOTICE("=" * 70))

