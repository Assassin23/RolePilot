# RolePilot — Career Page ATS Inspector Service
## Architecture & Technical Specification

---

## 1. System Mission, Boundaries & Responsibilities

The **Career Page ATS Inspector** is a dedicated, stateless FastAPI microservice focused exclusively on **identifying, probing, and verifying company career boards**. 

### 1.1 Strict Boundary Separation: Inspection vs. Harvesting
A clear architectural boundary is drawn between **career platform identification** and **job discovery/harvesting**:

```
┌────────────────────────────────────────────────────────┐
│      Career Page ATS Inspector (FastAPI Service)        │
│  • Career URL crawler & HTML signature analyzer        │
│  • ATS identification (Greenhouse, Lever, Ashby, etc.)  │
│  • Provider API live probe verification                │
│  • Stateless evaluation engine                         │
└──────────────────────────┬─────────────────────────────┘
                           │ Returns Verified Metadata
                           ▼
┌────────────────────────────────────────────────────────┐
│          RolePilot Core (Django & Orchestrator)        │
│  • Registry Authority (stores & enables boards)        │
│  • Independent Provider Adapters:                      │
│      - GreenhouseAdapter (per-company board discovery) │
│      - JobgetherAdapter (aggregator search API)        │
│  • Daily cap & rate limit enforcement                  │
│  • Normalization, deduplication, & candidate matching  │
└────────────────────────────────────────────────────────┘
```

1. **What the Inspector DOES**:
   - Takes a company career page URL or candidate domain.
   - Follows redirects safely with strict SSRF controls.
   - Extracts underlying ATS identifiers and platform signatures.
   - Issues a lightweight probe to the platform's public API to confirm validity, public availability, and published job count.
   - Returns a structured verification report to the caller.

2. **What the Inspector DOES NOT DO**:
   - **No Job Harvesting**: It does not ingest, parse full job descriptions, or store job listings.
   - **No Jobgether Discovery**: Jobgether daily querying (and its 100-job / 4-call limit) belongs exclusively to RolePilot Core's job discovery orchestrator, completely separated from this service.
   - **No Registry Lock-in**: The inspector is stateless; RolePilot Core remains the authoritative registry owner that persists and activates company boards.

---

## 2. Provider Separation: Greenhouse vs. Jobgether

Jobgether and Greenhouse are separated at both the **provider** and **responsibility** levels:

| Characteristic | Greenhouse Adapter | Jobgether Adapter |
| :--- | :--- | :--- |
| **Provider Type** | Per-company ATS Board | Aggregator Search API |
| **Discovery Mechanism** | Explicit verified company board slug (`/v1/boards/{token}/jobs`) | Query-based keyword & location search (`/api/v1/jobs?keyword=...`) |
| **Role of Inspector** | Discovers & verifies unknown company board slugs | **Not involved** (endpoint and search contract are fixed) |
| **Quota & Rate Limits** | Up to 100 jobs *per configured company board* | Strictly **100 jobs / 4 API calls per day total**, cached once daily |
| **Execution Responsibility** | RolePilot Core Orchestrator | RolePilot Core Orchestrator |

Neither provider's harvesting logic lives inside the Inspector.

---

## 3. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Caller_Layer [Consumers & Management]
        DjangoAdmin[Django Admin & Dashboard]
        MgmtCommand[CLI: python manage.py inspect_career_page]
    end

    subgraph Inspector_Service [FastAPI Career Page Inspector (Port 8001)]
        API_Router[REST Router: /api/v1/inspect]
        SSRF_Engine[DNS Pre-resolver & SSRF Firewall]
        HTML_Crawler[Streaming HTTP Fetcher (Max 2MB, 5 Redirects)]
        Signature_Matcher[Multi-ATS Signature Extractor]
        Prober_Registry[Provider Probers (Greenhouse, Lever, etc.)]
    end

    subgraph Target_Web [Public Web Targets]
        CompanyCareers[Target Company Career Page (HTML)]
        GreenhouseProbe[Greenhouse Public Board API]
    end

    subgraph Core_Storage [RolePilot Relational Storage]
        PostgresDB[(PostgreSQL / config/companies.yaml)]
    end

    Caller_Layer -->|POST /api/v1/inspect| API_Router
    API_Router --> SSRF_Engine
    SSRF_Engine -->|Validated Safe IP| HTML_Crawler
    HTML_Crawler -->|Fetch HTML| CompanyCareers
    HTML_Crawler --> Signature_Matcher
    Signature_Matcher -->|Extracted Slug| Prober_Registry
    Prober_Registry -->|Lightweight Probe GET| GreenhouseProbe
    Prober_Registry --> API_Router
    API_Router -->|Structured Verification Report| Caller_Layer
    Caller_Layer -->|Persist Verified Board| PostgresDB
```

---

## 4. Hardened Security & SSRF Prevention

Because the inspector fetches arbitrary external URLs submitted by users or configured lists, strict SSRF defenses are enforced:

### 4.1 DNS Resolution & IP Range Blacklisting
Before dispatching any HTTP request:
1. **Hostname Resolution**: Resolve the target hostname to its IP address via `socket.getaddrinfo()`.
2. **CIDR Blacklist Check**: Explicitly reject connections to any non-public IP ranges:
   - `0.0.0.0/8` (Broadcast / current network)
   - `10.0.0.0/8` (Private Class A)
   - `100.64.0.0/10` (Carrier-grade NAT)
   - `127.0.0.0/8` (Loopback / localhost)
   - `169.254.0.0/16` (Link-local / Cloud metadata: AWS, GCP, Azure)
   - `172.16.0.0/12` (Private Class B)
   - `192.168.0.0/16` (Private Class C)
   - `::1/128`, `fc00::/7`, `fe80::/10` (IPv6 loopback & link-local)
3. **DNS Rebinding Guard**: Re-validate the destination IP on every redirect hop.

### 4.2 Network & Transport Bounds
- **Allowed Schemes**: Only `http://` and `https://`.
- **Allowed Ports**: Only standard web ports `80` and `443`.
- **Max Redirect Hops**: Maximum 5 hops. Reject redirect loops.
- **Streaming Response Cap**: Stream response bodies with a hard limit of **2 MB**. Abort immediately if `Content-Length` or streamed bytes exceed 2 MB.
- **Strict Timeouts**: 8-second connection timeout, 10-second read timeout.

---

## 5. ATS Signature Detection & Verification

### 5.1 Multi-ATS Signature Matching
The engine inspects HTML meta tags, script tags, iframe embeds, and outbound links:

| ATS Provider | Signature Target | Detection Pattern |
| :--- | :--- | :--- |
| **Greenhouse** | Script Embed | `greenhouse\.io/embed/job_board\.js\?for=([a-zA-Z0-9_-]+)` |
| **Greenhouse** | Hosted Link / Iframe | `(?:boards|job-boards)\.greenhouse\.io/([a-zA-Z0-9_-]+)` |
| **Lever** | Hosted Link / Script | `jobs\.lever\.co/([a-zA-Z0-9_-]+)` |
| **Ashby** | Hosted Link / Embed | `jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)` |
| **Workday** | External Subdomain | `([a-zA-Z0-9_-]+)\.wd\d+\.myworkdayjobs\.com` |

### 5.2 Provider-Specific Live Probing
When a signature is identified, the service invokes the corresponding provider prober:
- **Greenhouse Prober**:
  - GET `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
  - Validates:
    - HTTP `200`: Active public board. Reads `meta.total` and returns `is_active: True`.
    - HTTP `404`: Board identifier invalid or deprecated. Returns `is_active: False`.
    - HTTP `403`: Requires authentication (Harvest API only). Returns `is_active: False, requires_auth: True`.
- **Other Providers (Lever, Ashby, Workday)**:
  - Returns ATS classification with status `UNSUPPORTED_PROVIDER` (informing the caller that the company uses Lever/Ashby, which are outside MVP scope).

---

## 6. Service API Contracts

### 6.1 Inspect Career URL
- **`POST /api/v1/inspect`**
- **Request Body**:
  ```json
  {
    "company_name": "Cloudflare",
    "careers_url": "https://www.cloudflare.com/careers/jobs/"
  }
  ```
- **Response Body (200 OK — Verified Greenhouse Board)**:
  ```json
  {
    "status": "VERIFIED",
    "company_name": "Cloudflare",
    "careers_url": "https://www.cloudflare.com/careers/jobs/",
    "detected_ats": "greenhouse",
    "board_identifier": "cloudflare",
    "api_endpoint": "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs",
    "is_api_accessible": true,
    "published_jobs_count": 142,
    "confidence": "HIGH",
    "evidence": "Detected script embed 'greenhouse.io/embed/job_board.js?for=cloudflare'; API probe returned HTTP 200 with 142 published jobs.",
    "inspected_at": "2026-10-12T07:20:00Z"
  }
  ```

- **Response Body (200 OK — Identified Non-Greenhouse ATS)**:
  ```json
  {
    "status": "UNSUPPORTED_ATS",
    "company_name": "Acme Corp",
    "careers_url": "https://acme.com/careers",
    "detected_ats": "lever",
    "board_identifier": "acmeworks",
    "api_endpoint": null,
    "is_api_accessible": false,
    "published_jobs_count": 0,
    "confidence": "HIGH",
    "evidence": "Outbound redirect to 'jobs.lever.co/acmeworks'. Lever is not supported in MVP.",
    "inspected_at": "2026-10-12T07:20:00Z"
  }
  ```

- **Response Body (200 OK — No ATS Signature Detected)**:
  ```json
  {
    "status": "NOT_FOUND",
    "company_name": "Unknown Startup",
    "careers_url": "https://example.com/careers",
    "detected_ats": "unknown",
    "board_identifier": null,
    "api_endpoint": null,
    "is_api_accessible": false,
    "published_jobs_count": 0,
    "confidence": "NONE",
    "evidence": "No known ATS iframe, script embed, or outbound redirection detected.",
    "inspected_at": "2026-10-12T07:20:00Z"
  }
  ```

### 6.2 Health Check
- **`GET /health`**
- Returns `{ "status": "healthy", "service": "rolepilot-inspector" }`.

---

## 7. Registry Ownership & Integration Flow

1. **Registry Authority**:
   - Django holds the authoritative company registry (`DiscoveryBoard` model and `config/companies.yaml`).
2. **Workflow**:
   ```
   User/Admin inputs URL in Django 
     ──▶ Django sends POST to http://inspector:8001/api/v1/inspect
     ──▶ Inspector returns verified status & board token
     ──▶ If VERIFIED (Greenhouse), Django saves/enables the board in Registry
     ──▶ Discovery Orchestrator can now poll the verified board
   ```
3. **No Redundant Infrastructure**:
   - Running in the same Docker network as `inspector:8001`, sharing project volume for configurations.

---

## 8. Inspector Code Layout

```
inspector/
├── __init__.py
├── main.py             # FastAPI app with CORS & exception handlers
├── router.py           # /api/v1/inspect route
├── schemas.py          # Pydantic request & response models
├── ssrf.py             # DNS pre-resolution & CIDR firewall
├── crawler.py          # Bounded HTTP streaming fetcher
├── detector.py         # Multi-ATS regex signature engine
├── probers/
│   ├── __init__.py
│   └── greenhouse.py   # Greenhouse public API prober
└── tests/
    ├── test_ssrf.py
    ├── test_detector.py
    └── test_probers.py
```
