# VerifyWise AI backend (Phase 5)

This local FastAPI service uses SQLAlchemy and SQLite to persist application data, document metadata, and structured extraction results. It provides password-based login, short-lived JWT bearer access tokens, backend-enforced role checks, authenticated document upload, private file storage, digital PDF extraction, bounded Tesseract OCR, and optional evidence-checked LLM extraction. Passwords are hashed using Argon2 through `pwdlib`; JWTs are signed with a locally configured secret using PyJWT.

The Lovable frontend's login, institution registration, application list/create/detail, document upload/list, and per-application validation views call this backend. Public registration creates Applicant / Institution accounts only; privileged roles remain controlled through trusted provisioning. Remaining prototype tools may still show labeled synthetic browser data. Regulatory rules are not included.

## Roles and access

- **Applicant / Institution:** can create and update their own applications, and list or view only their owned applications.
- **Official Reviewer:** can list and view all applications, access their documents, and record finding review decisions. This follows the Phase 3 global reviewer read permission; reviewer-to-application assignment is not implemented.
- **Rules Manager / Administrator:** can list and view application metadata. Document bytes and extracted text are restricted to owning applicants and Official Reviewers. Regulatory-rule APIs are not part of this phase.

An applicant who requests an application owned by someone else receives `404 Not Found`, so the API does not disclose whether that record exists. Unowned records from a Phase 2 database remain accessible to staff roles only. New applications created through the API are owned by the authenticated applicant.

## Requirements and setup on macOS

- Python 3.11 or newer
- `venv` and `pip`
- Tesseract OCR for scanned-page recognition (`brew install tesseract`); the backend still starts if Tesseract is absent.

From the repository root:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Generate a unique signing secret and put it in `backend/.env` as `JWT_SECRET_KEY`:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Do not commit `.env` or share the generated value. The API refuses to start if the secret is missing or shorter than 32 characters. `ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 15 and is limited to 1–60 minutes. The example `.env` contains no usable secret.

The SQLite database defaults to `backend/verifywise.db`. Private document files default to `~/.verifywise-ai/private_documents`, outside the repository and frontend assets. New storage directories and files are created with owner-only permissions. You can set `DOCUMENT_STORAGE_DIR` to another dedicated private directory outside the repository; an existing directory must already have owner-only permissions. The API refuses a storage directory inside or above the project tree. Relative database paths and `.env` are resolved from `backend/`.

`MAX_DOCUMENT_SIZE_BYTES` defaults to 10 MiB. `MAX_EXTRACTED_TEXT_CHARS` defaults to 2,000,000 characters to bound stored extraction output. OCR is limited by `PDF_MAX_PAGES`, `OCR_MAX_PAGES`, `OCR_DPI`, `OCR_MAX_PAGE_PIXELS`, `OCR_PAGE_TIMEOUT_SECONDS`, and `PDF_PROCESSING_TIMEOUT_SECONDS`. Digital and OCR text is labeled with source and page number; the original PDF remains unchanged. If Tesseract is not installed, the upload is retained and reports `ocr_unavailable`.

Structured extraction is optional. For Google Gemini, configure backend-only `LLM_API_KEY` with your Gemini API key, `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`, and `LLM_MODEL=gemini-3.8-flash`. The existing OpenAI-compatible adapter sends chat-completions JSON requests to that endpoint; no extra SDK or schema changes are needed. Keep the key only in `backend/.env`. `LLM_TIMEOUT_SECONDS` and `MAX_LLM_INPUT_CHARS` bound provider use. With either required value missing, the service starts normally and extraction requests are recorded as `provider_unavailable`. The provider receives document text as untrusted data. Returned values must validate against the schema and each populated value must have an exact evidence quote present in the extracted text; fabricated or inconsistent evidence is rejected. No provider key is returned by the API. If Gemini is unavailable or rejects a response, extraction records an explicit provider error; PDF text extraction and OCR remain independent of the LLM.

## Create the initial administrator securely

Institutions can register through `POST /api/auth/register` with an email and password of at least 12 characters. The endpoint always assigns the Applicant / Institution role, rejects extra role fields, and stores an Argon2 password hash. It does not issue a token; the user signs in through `POST /api/auth/login`. This endpoint cannot provision reviewers or administrators. After configuring `.env`, create privileged accounts by running the provisioning command from `backend/` as a trusted local operator. It prompts for the password twice without placing it in shell history and stores only an Argon2 password hash.

```sh
python -m app.cli create-user \
  --email admin@example.test \
  --role 'Rules Manager / Administrator'
```

Use an organization-controlled email for real deployments. The CLI can also provision the other roles by passing `Applicant / Institution` or `Official Reviewer`. Provisioning requires trusted shell access to the backend/database; there is no public way to assign a privileged role.

## Run the backend

With the virtual environment active and the current directory set to `backend`:

```sh
uvicorn app.main:app --reload
```

The health endpoint is <http://127.0.0.1:8000/health>. Interactive API documentation is at <http://127.0.0.1:8000/docs>.

Browser access uses bearer headers and does not rely on cookies. `CORS_ORIGINS` is a comma-separated exact-origin allowlist; local Vite origins on ports 5173, 3000, and 8080 are included by default. For another frontend origin, add its full scheme/host/port to `backend/.env`. Wildcard origins are not used.

## Authentication API

### `POST /api/auth/login`

Submit JSON credentials. Successful login returns a short-lived access token and user summary. Unknown email, wrong password, and inactive account use the same `401 Unauthorized` response.

```sh
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.test","password":"your-password"}'
```

Send the returned token on protected endpoints using `Authorization: Bearer <access_token>`. The API does not persist tokens or issue refresh tokens. Since tokens are stateless and short lived, there is no immediate token-revocation endpoint; deactivating a user blocks their requests immediately because the API checks the account in the database on every request. A future frontend should keep access tokens in memory rather than localStorage.

### `GET /api/auth/me`

Return the authenticated user's current role and active status. Requires a bearer token.

## Application API

All endpoints below except login require a bearer token. Request and response bodies use JSON. Application and document fields continue to match the Phase 2 API.

### `POST /api/applications`

Applicant only. Creates an application owned by the authenticated user. Optional `documents` entries store metadata only; they do not upload file bytes. Returns `201 Created`.

```sh
curl -X POST http://127.0.0.1:8000/api/applications \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"institution_id":"SYN-INST-9001","institution_name":"Example Synthetic College","category":"Extension of Approval","reference_number":"SYN-REF-9001","submitted_at":"2026-10-26","declared_faculty_count":42}'
```

### `GET /api/applications`

Applicants see only their own records. Official Reviewers and Rules Managers can list all records. Supports `offset` (default `0`) and `limit` (default `100`, max `500`).

```sh
curl 'http://127.0.0.1:8000/api/applications?offset=0&limit=20' \
  -H 'Authorization: Bearer <access_token>'
```

### `GET /api/applications/{id}` and `PATCH /api/applications/{id}`

Applicants can read and patch only their own applications; staff roles can read all applications. Patch remains applicant-only. Cross-applicant access returns `404`; an unknown ID also returns `404`. Successful reads/updates return `200`.

```sh
curl -X PATCH http://127.0.0.1:8000/api/applications/<application-id> \
  -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"institution_name":"Updated Synthetic College"}'
```

### `POST /api/applications/{id}/decisions`

Official Reviewer only. Records a finding status and audit event; the finding must belong to the application. Applicants and Rules Managers receive `403 Forbidden`.

```sh
curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/decisions \
  -H 'Authorization: Bearer <reviewer-access-token>' \
  -H 'Content-Type: application/json' \
  -d '{"finding_id":"<finding-id>","status":"Under Review","note":"Evidence checked."}'
```

## Document API

Every document endpoint requires a bearer token. Applicants can access documents only for their own applications. Official Reviewers can access documents for any application they are authorized to review under the current global reviewer permission. Rules Managers cannot access document bytes or extracted text. Document URLs are never public or returned as direct filesystem paths.

### `POST /api/applications/{application_id}/documents`

Upload a PDF as multipart form data with a `category` form field and `file` part. The API checks the filename extension, supplied MIME type when present, byte limit, `%PDF-` signature, and successful PDF parsing. It calculates SHA-256 from the actual uploaded bytes, stores a sanitized display filename, and uses a random server-generated storage key. Duplicate content is retained as evidence and flagged in metadata; the API does not reveal which other record matched it. A second document in the same category for one application returns `409 Conflict` under the current database constraint.

```sh
curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/documents \
  -H 'Authorization: Bearer <access_token>' \
  -F 'category=fire_safety' \
  -F 'file=@./fire-safety-certificate.pdf;type=application/pdf'
```

Successful upload returns `201 Created` with metadata, SHA-256, processing and extraction statuses, duplicate-hash flag, and whether private content is available. The storage key and filesystem path are not included.

### `GET /api/applications/{application_id}/documents`

List metadata for the selected application, including the original display filename, hash, size, timestamps, extraction status, and extracted text length. Extracted text is not included in the list response.

```sh
curl http://127.0.0.1:8000/api/applications/<application-id>/documents \
  -H 'Authorization: Bearer <access_token>'
```

### `GET /api/applications/{application_id}/documents/{document_id}/content`

Stream the original PDF as an authenticated attachment with `private, no-store` caching and `nosniff`. A document ID must belong to the application in the URL. The response never includes the internal storage path.

### `GET /api/applications/{application_id}/documents/{document_id}/extracted-text`

Return extracted digital/OCR text and its explicit processing status to an authorized applicant or Official Reviewer. Text labels each page as `Digital` or `OCR`. Encrypted, empty, corrupt, unavailable OCR, over-limit, and page failure cases include a status describing the limitation. Corrupt PDFs with a valid PDF header are retained privately with `Upload error`; invalid extensions, MIME types, signatures, empty byte streams, and oversized uploads are rejected.

### `POST /api/applications/{application_id}/documents/{document_id}/reprocess-text`

Retry the same bounded digital text/OCR extraction against the privately stored original PDF. This is intended for uploads that were retained with empty extracted text, such as scanned PDFs after Tesseract has been installed. Only the owning applicant or an Official Reviewer may call it. To preserve evidence provenance, the endpoint refuses documents that already have nonempty extracted text; it does not replace the uploaded PDF or run the LLM.

### `POST /api/applications/{application_id}/documents/{document_id}/structured-extraction`

Request an optional structured extraction from the stored page-labeled text. The response is persisted with provider/model, status, result or explicit error, and creation timestamp. Missing fields remain null. Populated fields include evidence and a page reference where available. Requests require the same access as other document endpoints.

```sh
curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/documents/<document-id>/structured-extraction \
  -H 'Authorization: Bearer <access_token>'
```

### `GET /api/applications/{application_id}/documents/{document_id}/structured-extractions`

List persisted extraction runs for an authorized document. Possible statuses include `complete`, `partial`, `uncertain`, `no_fields_found`, `no_text`, `provider_unavailable`, `provider_error`, `invalid_output`, `invalid_evidence`, and `input_too_large`.

## Database and migrations

Startup creates missing tables and applies additive migrations for `applications.owner_user_id` and document storage, text, and extraction timestamp columns. Structured extraction and Phase 6 regulatory tables are created without removing existing records. Phase 6 adds no columns to the existing application or document tables. Existing applications and document metadata are preserved. Legacy documents have no storage key or file contents and their content endpoint returns `404`; no files or ownership are guessed. `create_all` does not handle future column changes; introduce a migration tool before further schema evolution.

## Regulatory sources, reviewed rules, and checklists

Regulatory source APIs require the Rules Manager / Administrator role, except read-only source and checklist endpoints, which require authentication. Registration records title, issuing authority, version, optional HTTPS source URL, publication/effective dates, and retrieval date. The URL is metadata only: this backend does not fetch remote URLs or assume an AICTE portal/API exists. Local/private URL hosts are rejected. Only manager-authorized PDF uploads are ingested; institutional application uploads never enter the regulatory source registry. Source PDFs are size-limited, stored in a private subdirectory, and processed with the existing bounded PDF/OCR extractor into page-referenced searchable passages.

Register an authorized source version, upload its PDF, inspect its extracted passages, and mark it verified after human review:

```sh
curl -X POST http://127.0.0.1:8000/api/regulatory/sources \
  -H 'Authorization: Bearer <rules-manager-token>' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Synthetic Handbook","issuing_authority":"Synthetic Authority","source_url":"https://regulator.example.org/handbook.pdf","document_version":"2026.1","publication_date":"2026-01-15","effective_date":"2026-04-01"}'

curl -X POST http://127.0.0.1:8000/api/regulatory/sources/<source-id>/upload \
  -H 'Authorization: Bearer <rules-manager-token>' \
  -F 'file=@./authorized-handbook.pdf;type=application/pdf'

curl http://127.0.0.1:8000/api/regulatory/sources/<source-id>/passages \
  -H 'Authorization: Bearer <rules-manager-token>'

curl 'http://127.0.0.1:8000/api/regulatory/sources/<source-id>/search?query=faculty' \
  -H 'Authorization: Bearer <rules-manager-token>'

curl -X POST http://127.0.0.1:8000/api/regulatory/sources/<source-id>/verify \
  -H 'Authorization: Bearer <rules-manager-token>'
```

When configured with the existing backend `LLM_API_KEY`, `LLM_MODEL`, and optional `LLM_BASE_URL`, a Rules Manager can request a proposal from a specific extracted passage:

```sh
curl -X POST http://127.0.0.1:8000/api/regulatory/sources/<source-id>/proposals \
  -H 'Authorization: Bearer <rules-manager-token>' \
  -H 'Content-Type: application/json' \
  -d '{"application_category":"Extension of Approval","passage_id":"<passage-id>"}'
```

The proposal gets a server-generated rule ID and stores its source/version, exact quotation, clause/annexure when supported, page, category, requirement, conditions, required evidence, validation type/parameters, dates, uncertainty, and draft/manual-review status. A quotation that is not present in the cited passage is rejected. Unsupported clause references or dates are removed and flagged for review. The prompt treats source text as untrusted input and forbids outside knowledge. No paid calls are used by the tests.

Only Rules Managers can review or revise rules. Use `GET /api/regulatory/rules` to inspect versions, then `POST /api/regulatory/rules/{rule-version-id}/approve` and `/activate` to approve and activate a draft; `POST /api/regulatory/rules/{rule-version-id}/retire` retires approved/active versions. `POST /api/regulatory/rules/{rule-version-id}/revise` accepts the revised rule fields and creates a new immutable version in draft or manual-review state. The old active version remains effective until the new version is approved and activated; activation retires the previous active version while retaining its history. A source version can supersede a previous source by passing `supersedes_source_id` during registration. This marks the prior source inactive, removing its rules from checklists and requiring proposals based on the new, separately verified source.

Configure categories with `PUT /api/regulatory/categories`, for example `{"application_category":"Extension of Approval","enabled":true}`. Authenticated users can retrieve `GET /api/regulatory/checklists/{application-category}`. A checklist contains only active rules from currently verified sources with matching source-version snapshots. Each item labels itself `verified_regulatory` or `demo`; no demo requirements are seeded. Unconfigured categories return an empty checklist, so the system does not invent requirements when no verified source exists.

## Deterministic validation and cross-document findings

Applicants can run validation only for their own applications. Official Reviewers can run and read validation for applications under the existing global reviewer permission. Rules Managers cannot read application document evidence through these endpoints. Validation evaluates only supported rule types that are active, non-demo, category-matched, within their applicability dates, and tied to a currently verified source version. Draft, approved-but-inactive, retired, inactive-source, superseded-version, and unsupported rule types are not executed. Rule parameters are interpreted through allowlisted keys and operators; regulatory records never execute stored code.

Supported deterministic types:

- `presence`: provide `document_category` and optionally `field`. A missing required document is a mismatch; an unavailable mandatory extracted field is `unable_to_verify`.
- `date`: provide `document_category`, `field` (`issue_date` or `expiry_date`), and comparison (`not_expired`, `not_before`, or `not_after`). `not_before` and `not_after` also need an ISO `date` parameter.
- `numeric`: supports `faculty_count` with `equals`, `min`, or `max` and a numeric `expected` value. Optionally compare with an authorized `reference_record_id`.
- `text_match`: supports extracted text fields with `exact` or `contains` and an `expected` value. Optionally compare against an explicitly authorized reference record for institution name/ID.
- `manual_review`: emits a manual review result without attempting an automated decision.

Unknown parameters, unsupported conditions, unavailable values, and malformed rule configurations produce manual-review or unable-to-verify results. An explicitly referenced institutional record is used only when `is_authorized=true` and its institution ID matches the application. Existing reference rows default to unauthorized during migration; trusted operators must authorize records through their controlled data provisioning process. No institutional reference administration API is added in this phase.

The engine reads only validated structured extraction results already stored for the application's documents. Cross-document checks compare institution name/ID, document reference, dates, issuer, document type, and faculty count when at least two documents contain values. Missing values are skipped rather than treated as conflicts. Conflicts are marked for manual review and explicitly do not represent fraud determinations. Result snapshots retain document IDs, page numbers, extracted quotes, expected/observed values, and the exact regulatory rule version where applicable.

### `POST /api/applications/{application_id}/validation-runs`

Run deterministic checks and return a persisted summary plus per-check results. Requires an applicant who owns the application or an Official Reviewer.

```sh
curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/validation-runs \
  -H 'Authorization: Bearer <access_token>'
```

Run result statuses are `pass`, `mismatch`, `unable_to_verify`, and `manual_review`. The run status is `completed`, `completed_with_manual_review`, or `no_verified_rules`.

### `GET /api/applications/{application_id}/validation-runs` and `GET /api/applications/{application_id}/validation-runs/{run_id}`

Retrieve persisted run summaries and immutable per-run evidence snapshots. Each run is retained, including repeated runs with unchanged results.

### `GET /api/applications/{application_id}/findings`

Retrieve deduplicated actionable findings. Repeated identical issues reuse the existing finding ID while each run keeps its own result/evidence snapshot. Reviewer decisions and finding status are preserved. Finding statuses are `Open`, `Under Review`, `Resolved`, and `Escalated`.

## Official review, corrected documents, audit history, and reports

### Official finding review

Only an Official Reviewer can record an official finding decision. Applicants can read their findings and review history but cannot change them. Each decision requires a reason and records the reviewer, timestamp, previous workflow status, decision type, and note. Supported decisions are `confirmed_issue`, `dismissed_finding`, and `clarification_required`.

```sh
curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/findings/<finding-id>/reviews \
  -H 'Authorization: Bearer <reviewer-access-token>' \
  -H 'Content-Type: application/json' \
  -d '{"decision":"confirmed_issue","reason":"The cited evidence supports the finding."}'

curl http://127.0.0.1:8000/api/applications/<application-id>/findings/<finding-id>/reviews \
  -H 'Authorization: Bearer <access-token>'
```

### Corrected documents and smart revalidation

The original document upload remains unchanged. The owning applicant can upload corrected versions through `POST /api/applications/{application_id}/documents/{document_id}/corrections`; versions are stored privately and retained. Use `POST /api/applications/{application_id}/documents/{document_id}/corrections/{correction_id}/structured-extraction` to extract structured values when the backend LLM provider is configured, then run `POST /api/applications/{application_id}/validation-runs` again.

```sh
curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/documents/<document-id>/corrections \
  -H 'Authorization: Bearer <applicant-access-token>' \
  -F 'file=@./corrected-affiliation-certificate.pdf;type=application/pdf'

curl -X POST http://127.0.0.1:8000/api/applications/<application-id>/validation-runs \
  -H 'Authorization: Bearer <applicant-access-token>'
```

Each run retains an immutable evidence snapshot. Revalidation labels results `newly_detected`, `persistent`, or `resolved_by_new_evidence`. A corrected document that makes the same check pass marks the finding `Resolved` with `resolution_type=resolved_by_new_evidence`; a reviewer dismissal uses `resolution_type=dismissed_by_reviewer`. Neither path deletes prior findings, validation runs, evidence, or reviewer decisions. A correction without a successful structured extraction remains unable to verify.

### Audit history

`GET /api/applications/{application_id}/audit-history` returns application-scoped upload, validation, and review events to the owning applicant or an Official Reviewer. `GET /api/audit-history` returns global authorized regulatory source/rule/category events to Rules Managers only. These are read-only endpoints; there is no API to edit or delete audit entries. Earlier audit-log records remain visible alongside Phase 8 events.

### Application review report

`GET /api/applications/{application_id}/report` returns application details, the latest run, applicable rule/source references, findings with evidence and document IDs, verification records, and reviewer decisions. Run outcomes are labeled `Passed`, `Issue Found`, `Unable to Verify`, or `Manual Review Required`. The report identifies mock verification and the explicit synthetic-data flag and always states that it is not an official AICTE decision. Mock issuer checks remain mock and do not establish real issuer verification.

```sh
curl http://127.0.0.1:8000/api/applications/<application-id>/report \
  -H 'Authorization: Bearer <access-token>'
```

## Phase 8 database migration notes

Startup adds `document_corrections`, `document_correction_extractions`, and `audit_events` tables. It adds `applications.is_synthetic`, `reviewer_decisions.decision_type`, `validation_findings.resolution_type`, and `validation_run_results.revalidation_state` when missing. Existing findings, runs, reviewer decisions, documents, and audit logs are preserved. The migration does not remove the existing document-category uniqueness constraint; corrected PDFs use a separate versioned correction table, leaving the original upload and its history intact.

## Run tests

With the virtual environment active and current directory set to `backend`:

```sh
python -m pytest
```

Tests use isolated temporary SQLite databases and temporary private storage directories; they do not modify the local development database or home document store.
