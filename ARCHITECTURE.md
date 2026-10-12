# RolePilot — System Architecture & Specification

## 1. Requirements, Assumptions, and MVP Scope

### 1.1 Product Overview & Core Requirements
RolePilot is an automated personal job-discovery and candidate-matching platform designed to eliminate manual job searching and URL pasting.

Key functional requirements:
1. **Automated Discovery**: Fetch published opportunities systematically from configured source providers (Greenhouse company boards and Jobgether public API).
2. **Comprehensive Ingestion**: Ingest complete postings (titles, clean descriptions, raw HTML, departments, offices, locations, metadata) without premature client-side pre-filtering at the source.
3. **Architecture & Frameworks**:
   - Built with Python using a modular design.
   - Uses Django for persistent relational storage, candidate profiles, match review UI, and management commands.
   - Decoupled provider layer (`BaseJobProvider`) allowing sources to be added, tested, and toggled independently.
   - Includes a companion FastAPI Career Page ATS Inspector microservice (`rolepilot-inspector` on port 8001) to automatically detect and verify company career board identifiers.
4. **Independent Job vs. Candidate Separation**: Canonical job postings are shared, immutable records; candidate-specific evaluations (relevance scores, geographic eligibility, recommendation badges) are isolated per candidate profile.
5. **Conservative Location Eligibility**: Distinguish **work mode** (remote, hybrid, on-site) from **geographic eligibility** (legal/operational jurisdictions where employment is permitted). Uncertain geographic coverage must never be silently marked as eligible.
6. **Robust Error Isolation & Deduplication**: Failures in one provider or board must never halt processing for other sources. Job records are fingerprinted (SHA-256) to detect updates idempotently.
7. **Rate Limiting & Provider Quotas**:
   - **Jobgether**: Strictly capped at **100 jobs / 4 API calls per day**, with persistent daily disk caching.
   - **Company Boards (Greenhouse, etc.)**: Fetch up to **100 jobs per configured company board**, allowing multiple company boards to be discovered simultaneously.

### 1.2 Explicit Assumptions
- **Greenhouse Public Board Contract**: Greenhouse does not offer a cross-company global search endpoint. RolePilot maintains an explicit, configurable board registry (`config/boards.yaml`) of verified board tokens (e.g., `gitlab`, `cloudflare`, `canonical`).
- **Jobgether Public Search API**: Jobgether provides an unauthenticated developer search API (`https://jobgether.com/api/v1/jobs`) capped at 25 results per page. We limit collection to 4 calls (100 jobs) once per day and cache results to disk.
- **User Location Authority**: The user's explicit selection (Home Country ISO 3166-1 alpha-2 code and optional Home City) is authoritative. Device IP or geolocation inference is strictly avoided.
- **Technical Stacks vs. Spoken Languages**: "Language" refers strictly to programming languages (Python, Java, Go, TypeScript, C#, etc.). Spoken human languages (English, German, etc.) are ignored and do not disqualify candidates.
- **Out of Scope for MVP**: Automatic resume tailoring, auto-application submission, and web scraping of unpermitted sources.

---

## 2. Verified Job Discovery Sources

### 2.1 Greenhouse Job Board API
| Endpoint | Method | Auth | Query Parameters | Description |
| :--- | :--- | :--- | :--- | :--- |
| `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` | `GET` | None (Public) | `content=true` | Lists all published postings for the board with full HTML descriptions, departments, and offices. |

- **Quirks**: HTML entity-encoded descriptions (`&lt;div&gt;`), 404 for invalid board tokens (isolated per board), public rate-limit headers.

### 2.2 Jobgether Job Search API
| Endpoint | Method | Auth | Query Parameters | Description |
| :--- | :--- | :--- | :--- | :--- |
| `https://jobgether.com/api/v1/jobs` | `GET` / `POST` | None (Public) | `keyword`, `limit=25`, `page=1..4` | Returns remote/hybrid/onsite jobs matching keywords. |

- **Rate Limits & Caching Rules**:
  - `limit` is capped by Jobgether at 25 items per page.
  - RolePilot fetches at most **4 pages** (100 jobs max) once per 24-hour UTC window.
  - Persistent daily disk caching (`.cache/jobgether_daily_cache.json`): subsequent runs on the same date reuse cached results with zero network requests.

---

## 3. High-Level Architecture

```mermaid
flowchart TD
    subgraph Config_Layer [Configuration & Profiles]
        Registry[Board Registry: config/boards.yaml]
        CandidateProfile[Candidate Profile: IN / Bengaluru, Python, Go, Java]
    end

    subgraph Provider_Layer [Unified Provider Adapters]
        BaseProvider[BaseJobProvider Interface]
        GH_Adapter[GreenhouseAdapter]
        JG_Adapter[JobgetherAdapter (4 calls / 100 jobs / Daily Cache)]
        BaseProvider --> GH_Adapter
        BaseProvider --> JG_Adapter
    end

    subgraph Core_Engine [Orchestration & Analysis Engine]
        Orchestrator[DiscoveryOrchestrator: 100-Job Cap & Deduplication]
        Normalizer[Data Normalizer & SHA-256 Hasher]
        Analyzer[Analyzer: WorkMode & Skills Extraction]
        GeoEngine[Geographic Eligibility Engine: India/Bengaluru/Remote]
        MatchEngine[Multi-Stack Relevance Matcher: Tech Skills & Exclusions]
    end

    subgraph Data_Storage [Persistence & Cache]
        DiskCache[Disk Cache: .cache/jobgether_daily_cache.json]
        RelationalDB[(Relational DB: SQLite / PostgreSQL)]
    end

    subgraph UI_Runner [Interface & Execution]
        CLIRunner[CLI Demo Runner: python -m src.runner]
        DjangoAdmin[Django Admin & Candidate Dashboard]
    end

    Registry --> GH_Adapter
    JG_Adapter <--> DiskCache
    GH_Adapter --> Orchestrator
    JG_Adapter --> Orchestrator
    Orchestrator --> Normalizer
    Normalizer --> Analyzer
    Analyzer --> GeoEngine
    CandidateProfile --> MatchEngine
    GeoEngine --> MatchEngine
    MatchEngine --> Orchestrator
    Orchestrator --> RelationalDB
    Orchestrator --> CLIRunner
    RelationalDB --> DjangoAdmin
```

---

## 4. Data Models & Schemas

### 4.1 Canonical Job Schema (`src/schemas/job.py`)
```python
class CanonicalJob(BaseModel):
    id: str = Field(description="Deterministic UUID derived from source and source_job_id")
    source: str  # "greenhouse", "jobgether"
    source_job_id: str
    board_token: str
    company_name: str
    title: str
    description_raw_html: str
    description_clean_text: str
    job_url: str
    application_url: Optional[str] = None
    listed_locations: List[str] = Field(default_factory=list)
    publication_timestamp: Optional[datetime] = None
    source_update_timestamp: Optional[datetime] = None
    first_seen_timestamp: datetime
    last_seen_timestamp: datetime
    last_verified_timestamp: datetime
    content_fingerprint: str = Field(description="SHA-256 hash of normalized text")
    is_active: bool = True

    # Analysis Results
    work_mode: WorkMode = WorkMode.UNKNOWN
    work_mode_evidence: Optional[str] = None
    geographic_scope: GeographicScope = GeographicScope.UNKNOWN
    allowed_countries: List[str] = Field(default_factory=list)
    excluded_countries: List[str] = Field(default_factory=list)
    allowed_cities: List[str] = Field(default_factory=list)
    extracted_skills: List[str] = Field(default_factory=list)
    seniority_level: str = "UNKNOWN"
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
```

### 4.2 Candidate Profile & Match Result (`src/schemas/candidate.py`)
```python
class CandidateProfile(BaseModel):
    id: str = "candidate-1"
    name: str = "Candidate"
    home_country: str = "IN"  # ISO 3166-1 alpha-2
    home_city: Optional[str] = "Bengaluru"
    target_titles: List[str]
    primary_languages: List[str]       # e.g. ["Python"]
    alternative_languages: List[str]   # e.g. ["Go", "Java"]
    required_skills: List[str]         # e.g. ["PostgreSQL", "REST API"]
    preferred_skills: List[str]        # e.g. ["FastAPI", "Docker", "Redis"]
    excluded_keywords: List[str]       # e.g. ["Wordpress", "PHP", "Sales"]
    min_seniority: Optional[str] = None


class CandidateMatchResult(BaseModel):
    candidate_id: str
    job_id: str
    relevance_score: float             # 0.0 to 100.0
    recommendation: Recommendation     # MATCH, REVIEW, EXCLUDE
    eligibility_status: EligibilityStatus  # ELIGIBLE, INELIGIBLE, NEEDS_VERIFICATION
    eligibility_reason: str
    matched_titles: List[str]
    matched_languages: List[str]
    matched_skills: List[str]
    missing_skills: List[str]
    exclusion_reasons: List[str]
    explanation: str
```

---

## 5. Decision Rules: Location Eligibility & Multi-Stack Matching

### 5.1 Geographic Eligibility Heuristics (`src/matcher/geo_eligibility.py`)
1. **On-Site & Hybrid**:
   - Located in candidate's home country & specified city $\to$ `ELIGIBLE`.
   - Located in candidate's home country, but requires office attendance in a different city $\to$ `NEEDS_VERIFICATION`.
   - Located in a foreign country $\to$ `INELIGIBLE`.
2. **Remote Roles**:
   - Explicit exclusion of candidate's country (e.g. "US only", "Must reside in North America") $\to$ `INELIGIBLE`.
   - Explicit inclusion of candidate's country (e.g. "Remote - India") $\to$ `ELIGIBLE`.
   - Worldwide Remote ("Anywhere in the world", "Work from anywhere") $\to$ `ELIGIBLE`.
   - Regional scope covering candidate's country (e.g. "APAC Remote" for India) $\to$ `ELIGIBLE`.
   - Ambiguous/Unspecified bounds ("Remote" without specified payroll/jurisdiction) $\to$ `NEEDS_VERIFICATION`.

### 5.2 Multi-Stack Relevance Matching (`src/matcher/relevance.py`)
- **Exclusion Check**: Immediate `EXCLUDE` (Score: 0.0) if any excluded keyword matches.
- **Title Matching (35 pts)**: Exact target title match or related engineering alias.
- **Programming Language Stack (35 pts)**:
  - Primary language match (e.g. Python): 35.0 pts.
  - Acceptable alternative language match (e.g. Go, Java): 25.0 pts.
  - Neutral if unspecified: 15.0 pts.
  - Strictly different languages: 0.0 pts.
- **Required & Preferred Skills (30 pts)**: Proportional match of technologies (PostgreSQL, Docker, Redis, FastAPI, etc.).
- **Spoken Languages**: English, German, and human languages are completely ignored.

---

## 6. Implementation Status & Milestone Tracking

| Milestone | Scope & Deliverable | Status | Details |
| :--- | :--- | :---: | :--- |
| **Milestone 1** | **Core Schemas, Cleaner & Greenhouse Adapter** | **COMPLETED** | Pydantic schemas, HTML unescaping/tag stripping, SHA-256 fingerprinting, Greenhouse board adapter, error isolation. |
| **Milestone 2** | **Location Eligibility & Multi-Stack Matching** | **COMPLETED** | Geographic decision engine (`geo_eligibility.py`), multi-language relevance scoring (`relevance.py`), candidate profiles. |
| **Milestone 3** | **Unified Provider Layer & Jobgether Adapter** | **COMPLETED** | `BaseJobProvider` abstraction, `JobgetherAdapter` with 100-job / 4-call daily cap, disk caching (`.cache/jobgether_daily_cache.json`), 28 pytest tests passing. |
| **Milestone 4** | **Orchestrator & Interactive CLI Demo** | **COMPLETED** | `DiscoveryOrchestrator` enforcing deduplication and 100-job cap across providers, CLI runner (`python -m src.runner`) supporting simulation and live modes. |
| **Milestone 5** | **Relational Persistence (Database Layer)** | **COMPLETED** | Relational models (`CanonicalJobModel`, `DiscoveryRunModel`, `CandidateProfileModel`, `CandidateJobMatchModel`) with SQLite/PostgreSQL persistence and idempotent updates. |
| **Milestone 6** | **Django Management & Web Dashboard** | **COMPLETED** | Django management command (`python manage.py discover_jobs`), candidate onboarding UI, match review dashboard (`/`), run telemetry history (`/runs/`), and Docker containerization (`docker-compose.yml`). |
| **Milestone 7** | **Future: Resume Curation Tool Adapter** | **FUTURE** | Dedicated adapter to interface with the existing resume curation tool for tailored application material generation. |

---

## 7. Single-Command Docker Deployment

RolePilot is packaged for zero-setup execution using Docker Compose:

```bash
docker compose up --build
```

- Accessible at: `http://localhost:8000`
- Starts a dedicated `postgres:16-alpine` database container with healthcheck verification.
- Runs automatic database migrations against PostgreSQL on startup.
- Mounts persistent data volumes for PostgreSQL (`postgres_data`) and Jobgether daily cache (`rolepilot_cache`).
- Features in-browser discovery triggering, real-time filtering, candidate preference configuration, and telemetry inspection.
