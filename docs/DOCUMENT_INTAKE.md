# Document scans and personal upload links

Ported from `bernik1986/CV-for-seafarers`, reference commit
`306535cfebd4cdc4067046b2e3c7826a75b9f726`, into Manisov.
This workflow accepts document scans, not Word/Excel application forms.
Existing application parsers, document generation and submission archives
remain separate.

## Workflow

1. A recruiter or administrator opens a candidate and copies the personal
   upload link. The link can be revoked from the same candidate card.
2. The seafarer opens the link without a CRM account and uploads PDF/JPEG/PNG
   files, or groups ordered photos into a document. The link does not grant
   read access to the candidate or existing attachments.
3. New submissions appear in the candidate card and CRM Notifications.
4. A recruiter starts recognition, checks the preview, document type,
   number and dates, corrects uncertain fields, and explicitly saves them.
   Uploading by itself never changes confirmed CRM documents.

Local PDF extraction and Tesseract perform recognition. No external AI/OCR
provider is used. Check recognition results before approval. Ambiguous
types, dates and conflicts are flagged for review, not silently guessed.
Public uploads do not start OCR until a recruiter requests it.

## Limits and storage

- One submission: 40 files, 15 MiB per file, 45 MiB total.
- Supported formats: PDF, JPEG and PNG. OCR handles up to 20 pages.
- Pending public content: 64 MiB per candidate and 256 MiB overall.
- Shared temporary scan storage: 512 MiB.
- Private unapproved drafts expire after seven days and are cleaned on a
  later upload. Public received/in-review submissions remain until closed.
- Completing or discarding a submission releases temporary content.
  Confirmed attachments remain in the candidate record.
- Run one backend worker to keep the local OCR queue and resource limits
  predictable. Jobs resume after a restart.

Personal links are bearer secrets: anyone with a link can submit scans
for that candidate until it is revoked. Send them only to the intended
seafarer. The token is in the URL fragment and sent in a dedicated API
header, not in query strings. The anonymous client sends no CRM JWT.

## Enable locally

The two feature switches are checked on every request. Both are off by
default. In PowerShell, from the checkout root:

```powershell
New-Item -ItemType Directory -Force uploads
New-Item -ItemType File -Force uploads/.document-intake-enabled
New-Item -ItemType File -Force uploads/.document-upload-enabled
```

The Docker image includes Tesseract with English, Russian and Ukrainian.
On Windows install Tesseract locally; the recognizer also searches
`C:/Program Files/Tesseract-OCR/tesseract.exe`. Optional settings:
`DOCUMENT_INTAKE_TESSERACT` (executable path) and
`DOCUMENT_INTAKE_OCR_LANGS` (default `eng+rus+ukr`). Missing languages
produce review warnings; they do not trigger an external fallback.

## Production release

Do not point regression tests at production. Before releasing, save a
verified PostgreSQL dump plus uploads, templates, configuration and the
current Git SHA. Pause automatic deployment and application writes while
capturing a consistent production backup. The local workspace backup
described below is not a production database backup.

Rebuild the backend image (a restart alone does not install Tesseract),
apply `alembic upgrade head`, and start the application. The Docker entry
point already runs that migration command. The new revision is
`f1c4e92381ad`, after `b5c6d7e8f9a0` (existing comment reminders).
After verifying the release and public HTTPS endpoint, enable switches:

```sh
docker compose exec -T backend touch /app/uploads/.document-intake-enabled
docker compose exec -T backend touch /app/uploads/.document-upload-enabled
```

The external proxy must expose `/upload-documents` as an anonymous SPA
route and `/api/public/document-upload` as an anonymous API route. The
API still requires a valid personal token. Allow at least 45 MiB plus
multipart overhead (the existing nginx limit is 100 MiB).

First recovery action, without removing already approved documents:

```sh
docker compose exec -T backend rm -f /app/uploads/.document-upload-enabled
docker compose exec -T backend rm -f /app/uploads/.document-intake-enabled
```

This stops new public uploads and pauses OCR between files. It is not a
database rollback. Downgrading to `b5c6d7e8f9a0` drops the three new scan
tables and their pending submissions/links. Do not do that on production
without a fresh backup and an explicit decision about pending files.

## Verified local rollback snapshot

Before the port, a snapshot was saved to:
`backups/before-seafarer-intake-20261120T154713Z`.
It contains 402 files, including existing uncommitted changes, local
SQLite snapshots and runtime files. Each archived file has a SHA-256
checksum. Git history is in `history.bundle`; `head.txt`, `status.txt`
and `working-tree.patch` describe the starting state.

Restore into a **new, nonexistent directory**, never over a running app:

```powershell
python scripts/restore_workspace.py backups/before-seafarer-intake-20261120T154713Z generated/restored-before-intake
```

The script verifies all checksums before extraction and refuses an
existing destination. Stop local services before switching to the
restored copy. Dependencies can be reinstalled separately; they are not
included in the archive. Restore was exercised in
`generated/rollback-verified`. Do not upload these private backups to Git.

For another snapshot:

```powershell
python scripts/backup_workspace.py
```

## Isolated regression checks

Use a new disposable SQLite path when running pytest, with startup
migrations/reset explicitly disabled. The Playwright configuration
starts its own backend/frontend on ports 18080/15173, uses a unique
database and storage below `.playwright/`, enables both feature switches
there, and refuses to reuse an existing server. Override ports with
`PW_API_PORT` and `PW_WEB_PORT` when necessary. It never uses the regular
`maritime_parser.db` or `uploads/`.

```powershell
$env:DATABASE_URL='sqlite:///./generated/intake-regression.db'
$env:AUTO_ALEMBIC_ON_STARTUP='0'
$env:RESET_DB_ON_START='0'
python -m pytest -q
npx playwright test
```

The new browser workflow is in
`e2e/tests/document-upload-recognition.spec.cjs`.

## Verification record (2026-11-20)

- Before the port: 315 backend tests passed, one skipped.
- Final complete backend suite: 449 passed, one skipped (the original
  Reshetov DOCX sample on the external G: drive is unavailable).
- Final full browser suite: 69 passed, four skipped. Those four require
  additional list rows, a nonempty list, a selectable generation template
  or company salary rates in the disposable database.
- Dedicated scan-review browser suite: 15 passed, no skips.
- Production frontend build and Linux Docker build passed. Vite reports
  the existing-style large main bundle warning; no build errors.
- Real OCR was exercised on PNG, JPEG and PDF. A separate Linux/PostgreSQL
  smoke test verified public upload, inbox, actual OCR, private preview,
  explicit approval, attachment download, idempotent replay and revocation.
- PostgreSQL upgrade from the previous schema, downgrade and re-upgrade
  preserved a synthetic existing candidate. Existing SQLite comments and
  foreign keys were checked during startup compatibility tests.
- The rollback archive was restored and every file checksum verified;
  `git bundle verify` confirmed complete history.

Regression work also fixed stale scan replacement, unlimited-document
expiry cleanup, quota checks before photo conversion, stale candidate
responses hiding an uploaded photo, profile date persistence, and missing
actor attribution in the hyphenated sea-service update route. Older E2E
selectors were aligned with the existing table columns and Russian labels.

The local demonstration runs at `http://127.0.0.1:5173/candidates/1`, with
backend port 18082. Login: `admin` / `admin123` (local test account only).
Its data lives in `.playwright/intake-preview-20261120`; it does not use
the regular CRM database. Both feature markers are enabled there.
These localhost links cannot be sent to an external seafarer for real use.
Production and GitHub have not been updated by this implementation task.
