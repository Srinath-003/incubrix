# IncuBrix Distribution Network

> **IncuBrix Distribution: Long-Tail Destination Network**  
> Scalable, resilient distribution engine connecting digital content renditions to specialized, long-tail publishing destinations.

---

## 1. Overview & Phase 2 Capabilities

Phase 2 builds upon the Phase 1 architectural foundation by establishing:
- **Connector Framework & Central Registry**: Centralized connector lifecycle management supporting automated and assisted execution tiers, manifest validation, duplicate-key prevention, and structured disabled-state handling.
- **Discourse Destination Connector**: Production-grade platform adapter implementing topic creation (`POST /posts.json`), post status inspection, and safe deletion with SSRF protection and credential isolation.
- **Safe Simulation Mode**: Explicit, deterministic simulation mode guaranteeing **zero external HTTP requests**, reproducible mock post IDs (`sim_discourse_...`), and isolated in-memory test state.
- **Safe Publish Idempotency**: Cryptographically-hashed request tracking (SHA-256 excluding sensitive credentials), MongoDB unique compound indexing with isolated repository fallback, concurrent duplicate request conflict detection, and ambiguous timeout reconciliation.
- **Pre-Publish Policy Hook**: Reusable posting rule enforcement checking destination frequency caps, self-promotion restrictions, external link constraints, and AI disclosure requirements prior to dispatch.

---

## 2. Directory Architecture

```
incubrix/
├── app/
│   ├── __init__.py
│   ├── main.py                     # Application factory, lifespan context, logging filters
│   ├── config.py                   # Environment settings (SIMULATION_MODE, ALLOW_LOCAL_DESTINATIONS)
│   ├── core/
│   │   ├── database.py             # MongoDB client lifecycle, health ping, and collection constants
│   │   ├── errors.py               # Standard error codes and ErrorEnvelope domain exceptions
│   │   ├── handlers.py             # Global exception handlers formatting the error envelope
│   │   └── security.py             # SSRF destination URL validation & recursive credential redactor
│   ├── models/
│   │   ├── common.py               # Rendition, Destination, Connection, ConnectorTier
│   │   ├── manifest.py             # ConnectorManifest, ConnectorCapabilities, method validation
│   │   └── connector.py            # Authoritative Appendix A request and response schemas
│   ├── connectors/
│   │   ├── base.py                 # Abstract BaseConnector interface (Appendix A contract)
│   │   ├── registry.py             # ConnectorRegistry with duplicate-key & disabled enforcement
│   │   └── discourse/
│   │       ├── __init__.py         # DiscourseConnector export
│   │       └── connector.py        # Discourse adapter (validate, publish, get_status, delete)
│   ├── simulation/
│   │   ├── store.py                # Dedicated in-memory simulation state isolated between tests
│   │   └── adapter.py              # Zero-HTTP simulation execution adapter
│   ├── idempotency/
│   │   └── repository.py           # Durable & in-memory idempotency repository with SHA-256 hashing
│   ├── policies/
│   │   └── rules.py                # Pre-publish policy hook (frequency caps, promo, links, AI)
│   └── api/
│       ├── router.py               # Root API router aggregation
│       └── routes/
│           ├── health.py           # GET /health (liveness) & GET /ready (readiness)
│           ├── connectors.py       # GET /api/v1/connectors & GET /api/v1/connectors/{key}/manifest
│           └── connector_rpc.py    # POST /connector/v1/{connector_key}/{method}
├── tests/                          # Automated pytest suite (72 tests)
│   ├── conftest.py                 # Fixtures, test client, and registry/store isolation
│   ├── test_config.py              # Configuration loading and secret protection tests
│   ├── test_connector_contract.py  # Appendix A signature and tier execution tests
│   ├── test_connector_rpc.py       # RPC route dispatch and error response tests
│   ├── test_discourse_connector.py # Discourse validation, request mapping, error handling
│   ├── test_errors.py              # Standard error envelope serialization tests
│   ├── test_health.py              # Liveness and readiness probe verification
│   ├── test_idempotency.py         # Publish idempotency, key conflicts, concurrency, timeouts
│   ├── test_manifest.py            # Manifest validation rules and tier constraints
│   ├── test_posting_rules.py       # Pre-publish posting policy verification
│   ├── test_registry.py            # Central registry registration and query tests
│   ├── test_registry_and_rpc_phase2.py # Disabled connectors, SSRF prevention, credential redaction
│   └── test_simulation_mode.py     # Safe zero-HTTP simulation tests and lifecycle
├── docker-compose.yml              # Container orchestration (MongoDB 7.0 + FastAPI service)
├── Dockerfile                      # Container build definition (Python 3.11-slim)
├── .dockerignore                   # Build context exclusions protecting venv and cache
├── .env.example                    # Environment variable configuration template
├── pyproject.toml                  # Python package and dependency configuration
└── requirements.txt                # Pinned dependencies
```

---

## 3. Connector Framework & Registry

Connectors are strictly **stateless platform adapters**. They **never write directly to IncuBrix's internal database**. All database persistence (jobs, idempotency, event logs) is coordinated by the API and service layers.

### Central Registry (`ConnectorRegistry`)
- Registered connectors must have unique keys (`[a-z0-9_-]+`). Attempting to register an existing key raises `DUPLICATE_CONNECTOR` (HTTP 409).
- Connectors can be dynamically enabled or disabled via `registry.disable(key)` and `registry.enable(key)`.
- Querying or invoking an unknown connector returns HTTP 404 with error code `CONNECTOR_NOT_FOUND`.
- Invoking a disabled connector returns HTTP 403 with error code `CONNECTOR_DISABLED`.

---

## 4. Simulation Mode

Simulation mode is designed for safe automated testing and local development without requiring live platform accounts, external API keys, or public posts.

### Key Guarantees
- **Zero Outbound HTTP Requests**: All publish, status, and delete operations execute against an in-memory simulation store.
- **Deterministic Mock Identifiers**:
  - Mock post IDs follow the format: `sim_{platform}_{sha256(idempotency_key)[:10]}` (e.g., `sim_discourse_3a4f89b1c2`).
  - Mock URLs follow: `{instance_url}/t/simulated-{platform}-post/{post_id}`.
- **No Fallback**: If `SIMULATION_MODE=false` and a network error occurs, the engine **never silently falls back** to simulation mode. It surfaces the authentic platform error (`PLATFORM_UNAVAILABLE`, `RATE_LIMITED`, etc.).
- **Isolated State**: The simulation store can be cleared cleanly between test runs (`simulation_store.clear()`), ensuring total test isolation.

### Configuration
Simulation mode is controlled via `.env`:
```ini
# Enabled by default for safe local development
SIMULATION_MODE=true
```

---

## 5. Safe Publish Idempotency

Publishing operations enforce strict idempotency to prevent duplicate posts across network retries and distributed workers:

1. **Request Hashing**: A canonical SHA-256 hash is computed from `rendition` and `destination`. **Credentials and authentication tokens are strictly excluded** from the hash and are never stored in the idempotency record.
2. **Duplicate Requests (Same Key, Same Payload)**: The original publish response is stored upon completion. Subsequent identical requests return the cached result immediately without invoking the platform connector.
3. **Conflicting Requests (Same Key, Different Payload)**: If an idempotency key is reused with a differing payload, the API immediately returns HTTP 409 with error code `IDEMPOTENCY_CONFLICT`.
4. **Concurrent Requests**: Simultaneous racing requests for the same key acquire an atomic `in_progress` reservation. Competing requests receive an `IDEMPOTENCY_CONFLICT` stating that the operation is already in progress.
5. **Ambiguous Timeouts**: If a network timeout occurs while awaiting platform confirmation, the record is flagged as `uncertain`. Subsequent retries return HTTP 504 `AMBIGUOUS_TIMEOUT` to prevent duplicate creation until manual or reconciliation resolution is performed.
6. **Header Reconciliation**: The `Idempotency-Key` HTTP header is supported across all POST routes. If both header and body keys are provided, they must match; conflicting values produce HTTP 409 `IDEMPOTENCY_CONFLICT`.

---

## 6. Pre-Publish Posting Rules

Before any platform request is dispatched, the `PolicyEngine` validates destination-specific posting constraints:

| Policy Rule | Destination Setting | Violation Trigger |
| :--- | :--- | :--- |
| **Frequency Cap** | `frequency_cap_exceeded: true` | Flags destination posting threshold reached |
| **Self-Promotion** | `prohibit_self_promotion: true` | Rejects promotional phrasing (`buy now`, `special discount`, `promo code`, `affiliate link`) |
| **Link Restrictions** | `prohibit_links: true` or `max_links: N` | Rejects content containing external URLs or exceeding maximum link count |
| **AI Disclosure** | `require_ai_disclosure: true` | Requires disclosure markers (`#ai`, `[AI]`, `ai-generated`) when content is marked AI-generated |

Violations return HTTP 422 with code `POLICY_VIOLATION` containing structured violation details. The publishing operation cannot bypass this hook.

---

## 7. Discourse Destination Connector

The Discourse adapter connects IncuBrix to Discourse forums using the documented REST API.

### Manifest Summary
```json
{
  "connector_key": "discourse",
  "name": "Discourse Forum Connector",
  "version": "1.0.0",
  "tier": "automated",
  "platform": "discourse",
  "auth_type": "api_key",
  "supported_methods": ["validate", "publish", "get_status", "delete"],
  "capabilities": {
    "media_types": ["video", "image", "text", "link"],
    "max_file_size_bytes": 52428800,
    "max_duration_sec": 300,
    "supports_delete": true,
    "custom_limits": {
      "min_title_length": 5,
      "max_title_length": 255,
      "min_body_length": 10
    }
  },
  "supported_surfaces": ["topic", "post"],
  "rate_limits": {"posts_per_minute": 20, "burst": 5},
  "auth_requirements": {
    "api_key": "Discourse API Key (global or user key)",
    "api_username": "Discourse API Username (or system)"
  },
  "instance_parameters": {
    "instance_url": "Base URL of Discourse forum (e.g. https://discourse.example.com)",
    "category": "Discourse Category ID (integer) or category slug"
  }
}
```

### Authentication & Security
- Uses `Api-Key` and `Api-Username` HTTP headers.
- **SSRF Protection**: Destination URLs are validated against private, loopback, link-local, and cloud metadata addresses (`169.254.169.254`, `127.0.0.1`, `10.x`, etc.). Local testing requires explicitly setting `ALLOW_LOCAL_DESTINATIONS=true`.
- **TLS Verification**: Production code never disables SSL/TLS verification (`verify=True`).
- **Safe Deletion**: Deletion requires simulation mode or an explicitly configured owned test instance (`DISCOURSE_TEST_URL`) to prevent accidental destruction of public content.

---

## 8. RPC Route Patterns & Examples

All connector contract methods are invoked via HTTP POST:
```http
POST /connector/v1/{connector_key}/{method}
Content-Type: application/json
Idempotency-Key: <optional-header-key>
```

### 1. `validate`
**Request:**
```json
POST /connector/v1/discourse/validate
{
  "rendition": {
    "title": "Scaling Distributed Systems",
    "caption": "A technical breakdown of scaling stateful and stateless services.",
    "media_type": "text"
  },
  "destination": {
    "platform": "discourse",
    "settings": {
      "instance_url": "https://discourse.example.com",
      "category": 1
    }
  },
  "connection": {
    "auth_type": "api_key",
    "credentials": {
      "api_key": "disc_api_key_sample",
      "api_username": "moderator"
    }
  }
}
```
**Response (HTTP 200):**
```json
{
  "ok": true,
  "violations": []
}
```

### 2. `publish`
**Request:**
```json
POST /connector/v1/discourse/publish
Header: Idempotency-Key: idem-pub-2026-001
{
  "rendition": {
    "title": "Scaling Distributed Systems",
    "caption": "A technical breakdown of scaling stateful and stateless services.",
    "tags": ["architecture", "scaling"]
  },
  "destination": {
    "platform": "discourse",
    "settings": {
      "instance_url": "https://discourse.example.com",
      "category": 1
    }
  },
  "connection": {
    "auth_type": "api_key",
    "credentials": {
      "api_key": "disc_api_key_sample",
      "api_username": "moderator"
    }
  },
  "idempotency_key": "idem-pub-2026-001"
}
```
**Response (HTTP 200 in simulation mode):**
```json
{
  "platform_post_id": "sim_discourse_e3b0c44298",
  "live_url": "https://discourse.example.com/t/simulated-discourse-post/sim_discourse_e3b0c44298",
  "status": "published"
}
```

### 3. `get_status`
**Request:**
```json
POST /connector/v1/discourse/get_status
{
  "platform_post_id": "sim_discourse_e3b0c44298",
  "connection": {
    "auth_type": "api_key",
    "credentials": {}
  }
}
```
**Response (HTTP 200):**
```json
{
  "status": "published",
  "live_url": "https://discourse.example.com/t/simulated-discourse-post/sim_discourse_e3b0c44298"
}
```

### 4. `delete`
**Request:**
```json
POST /connector/v1/discourse/delete
{
  "platform_post_id": "sim_discourse_e3b0c44298",
  "connection": {
    "auth_type": "api_key",
    "credentials": {}
  }
}
```
**Response (HTTP 200):**
```json
{
  "deleted": true
}
```

### Standard Error Response Envelope
All application errors follow the uniform schema:
```json
{
  "error": {
    "code": "IDEMPOTENCY_CONFLICT",
    "message": "Idempotency key 'idem-pub-2026-001' was previously used with a different request payload.",
    "retryable": false,
    "details": {
      "idempotency_key": "idem-pub-2026-001",
      "connector_key": "discourse"
    }
  }
}
```

---

## 9. Running Tests & Local Verification

### Running the Pytest Suite
Execute the entire test suite (72 automated tests):
```bash
pytest -q
```
Or with verbose details:
```bash
pytest -v
```

### Running with Docker Compose
To launch MongoDB and the IncuBrix FastAPI engine:
```bash
docker compose up -d
```
Check health endpoints:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

## 10. Configuring an Owned Discourse Test Instance

To test against an authentic, owned Discourse instance (rather than simulation mode):

1. **Obtain API Credentials**:
   - Navigate to your Discourse Admin panel: `Admin -> API -> Keys`.
   - Generate an API Key with `Global` or `Topic Creation` scope.
   - Note the API Username (typically `system` or an administrative user).
2. **Configure Environment**:
   ```ini
   SIMULATION_MODE=false
   ALLOW_LOCAL_DESTINATIONS=true   # Only if Discourse runs on localhost
   DISCOURSE_TEST_URL="http://localhost:4200"  # Or your owned forum URL
   ```
3. **Execute Integration Publish**:
   - Issue a request to `/connector/v1/discourse/publish` pointing `destination.settings.instance_url` to your owned test instance.

---

## 11. Known Limitations & Phase 3 Roadmap

- **Phase 3 Connectors Out of Scope**: Lemmy, Dev.to, Ghost, HMAC webhooks, and Assisted tier connectors are not implemented in Phase 2.
- **AI Content Scoring & Recommendation**: Heuristic and LLM-based distribution routing will be added in Phase 3.
- **Batch CSV Import**: Destination bulk onboarding belongs to subsequent milestones.
- **Durable Distributed Locking**: When MongoDB is connected, compound unique indexes enforce idempotency; for multi-region active-active topologies, Redis or distributed consensus leases would further minimize race windows under high write concurrency.
