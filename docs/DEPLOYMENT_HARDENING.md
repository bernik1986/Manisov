# Release and Recovery Contract

This is the deployment contract, not proof that a particular host is configured.
Complete the one-time migration below before enabling either release entry point.
The legacy timer wrapper is incompatible with this release procedure. Do not run
an old timer alongside the new scripts. Keep host-specific checks and recovery
records in protected operator storage, not in the public repository.

## One-time administrator migration

1. Inspect `systemctl cat manisov-deploy.timer manisov-deploy.service` and the old
   wrapper. Disable the timer and wait for any active deployment to finish. Do not
   cancel a running migration. Record the old units/wrapper for recovery.
2. On the host, inspect the current Compose project label and PostgreSQL mount.
   Set `.env` `COMPOSE_PROJECT_NAME` and `POSTGRES_VOLUME` to those EXACT existing
   values, not guessed defaults. The volume is external: deployment cannot create
   an empty replacement. The DB must already be healthy; deploy never replaces,
   upgrades, starts, or drops it. PostgreSQL resource limits and removal of any
   old host DB port require a separately planned DB service update.
   Preflight compares the existing DB's POSTGRES_DB/USER/PASSWORD, the existing
   backend's DATABASE_URL, and all three backend bind mount sources against the
   proposed config before stopping anything. Data relocation or DB credential
   rotation is a separate planned operation, not a normal release flag change.
3. Set `DATA_DIR` to the existing parent of `uploads`, `generated`, and `templates`.
   All three directories must exist. Preserve shipped templates and manager files.
   Deployment changes their ownership to UID/GID 10001 and modes to 750/640 after
   backup. Symlinks and special files are rejected. The host needs capacity for
   both images, a full DB dump, and an uploads/templates archive on every release.
4. Put production secrets in the host `.env` (mode 600). Set a random JWT secret
   of at least 32 characters, explicit admin username, and a non-default password
   of at least 8 characters. `DATABASE_URL` must match this Compose DB, user and
   password (URL-encode credentials); external DB URLs are intentionally rejected.
   `MANISOV_ENV=production` is fixed in Compose. `CORS_ALLOWED_ORIGINS` defaults
   empty; configure explicit origins only when needed.
5. Provision Linux Bash, Python >=3.11.8, Git, util-linux `flock`, GNU tar/coreutils,
   and Docker Compose v2 with `up --wait`, `--wait-timeout`, and JSON config support.
   Create root-owned `/etc/manisov/deploy.env`, mode 600, with these systemd
   EnvironmentFile entries (no shell commands or shell sourcing):

   ```ini
   APP_DIR=/var/www/Manisov
   ENV_FILE=/var/www/Manisov/.env
   STATE_DIR=/var/lib/manisov-deploy
   LOCK_FILE=/var/lock/manisov-deploy.lock
   GITHUB_REPOSITORY=OWNER/REPOSITORY
   GH_TOKEN=HOST_READ_ONLY_TOKEN_IF_PRIVATE
   QUIESCENCE_CONFIRMED=yes
   ```

   Repository visibility is unknown. For a private repository the host token needs
   Actions read access to this repository; repository fetch authentication must
   also already work. For public repositories the token is optional but avoids
   unauthenticated rate limits. CI lookup failures, 401/403/404, and missing checks
   fail closed, without printing tokens or response bodies. Do not enable shell
   tracing or print the environment. Never put this token in Git or application
   containers.

   `QUIESCENCE_CONFIRMED=yes` is a static administrator assertion: this Compose
   backend is the only DB/file writer and external import/cron/worker jobs cannot
   write during releases. Disable or coordinate such jobs before setting it. The
   script stops frontend/backend, disables their restart policy, and rejects other
   live DB connections before snapshotting, but cannot fence arbitrary future
   clients. Do not assert this on a shared writable DB.
6. From the reviewed release, explicitly run as root:
   `ACK_TIMER_MIGRATION=yes bash scripts/install_deployment.sh`.
   It installs the trusted launcher/helpers, new systemd units, and the wrapper at
   `/usr/local/bin/manisov-auto-deploy.sh`. It does NOT start a deploy or enable a
   timer. Review any unit drop-ins, timer target, service environment, and sudo
   policy before deliberately re-enabling the existing timer. The installed
   launcher/helpers are trusted infrastructure: update them explicitly when their
   contract changes, not by `git reset` in an unattended wrapper.
7. For Actions, configure `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, and pinned
   `VPS_KNOWN_HOSTS`; grant only the required systemctl privilege. Do not use
   `ssh-keyscan` as an unauthenticated trust decision. Configure the production
   environment approval/protection policy. A missing complete SSH configuration
   leaves delivery to the newly installed timer, never to an untested fallback.

Fresh installations must explicitly create/provision the DB volume and service,
seed the host template directory, and set the project identity before deployment.
Existing installations must never use volume creation as a repair for a mismatch.

## Release sequence

Both entry points take the SAME `/var/lock/manisov-deploy.lock` internally. Do not
wrap them in a second `flock` on that file. The timer resolves `origin/main` inside
the lock; Actions passes its exact 40-character SHA to a durable systemd instance.
The source worktree is never reset or overwritten, even if dirty. Only a Git
archive of the tested commit is built; uncommitted changes are not deployable.

Admission requires the latest trusted main-branch run of `.github/workflows/deploy.yml`
for this exact SHA to have a completed successful `verify` job. A newer failed or
unfinished attempt blocks release. Both entry points use this guard, including
when SSH deployment is disabled. Verification covers pytest, deployment/migration
tests, frontend build/audit/browser tests, and the production image smoke check.
Stale queued SHAs are rejected once origin/main moves; code rollback is an explicit
operator procedure, not a routine old-SHA deployment.
`cancel-in-progress` is false; a disconnected SSH session does not own the server
process. Manual systemd termination still leaves recovery state after migration.

Both images build while the old app stays online. Images are then addressed by
local content ID, not mutable tags. Source archives become read-only. After
quiescing writers, the script creates a custom-format `pg_dump`, checks its table
of contents, archives uploads/templates, and records SHA-256 checksums and previous
container metadata. A `COMPLETE` marker is written only after both backups succeed.
Backups contain personal data and possibly previous environment secrets: restrict
access, encrypt off-host copies, and apply an explicit retention policy. Generated
downloads are disposable and excluded from backup; parent owns their cleanup.
New response artifacts are deleted after transmission, including disconnected
downloads, with a one-hour orphan sweep and storage/concurrency limits. Legacy
flat files under `generated` are intentionally NOT swept: inspect and inventory
them during the first maintenance window, then explicitly archive or remove only
confirmed disposable outputs. Do not recursively delete this directory: local
verification reports or operator-owned files may also be present.

Only then are data permissions prepared and Alembic run in the NEW image. Startup
auto-migration is disabled. Backend `/healthz` must pass before frontend starts;
nginx must serve both the SPA and `/api/healthz`. After success, the release pointer
is atomically updated and restart policies are enabled. Compose's deliberate
`restart: "no"` default prevents a failed candidate restarting after host reboot.
Do not bypass the launcher with ad-hoc `compose up` on production.

## Failure and rollback

- Before stopping services: failure leaves the old release serving normally.
- After stop but BEFORE migration: failure restarts existing old containers only;
  it never replaces them or restores data. If restart fails, maintenance remains.
- Once migration starts: ANY failure stops candidate services and leaves a durable
  maintenance marker. Timer/Actions attempts refuse to continue. No automatic
  Alembic downgrade, old-code restart, DB restore, or file restore occurs. SIGKILL,
  power loss, or lost Docker connectivity require operator inspection; the marker
  and disabled restart policy are the recovery boundary, not a transaction claim.
- After traffic returns: writes may already exist. Never replace the DB with the
  pre-migration dump as an automatic rollback. A verified forward fix is preferred.

Recovery requires the timer disabled, all writers quiesced, and the shared lock
held by the operator. Inspect journal output, `maintenance`, backup checksums,
Alembic revision, and previous image IDs. Rehearse compatibility on an isolated
restore. Code-only rollback is allowed ONLY after establishing that the old code
can read/write the current schema and data; retain the current DB/files. An old
image may auto-migrate on startup, so explicitly disable that behavior and inspect
its entrypoint first. Choose either a reviewed forward release or a verified
code-only rollback, start with no public ingress, check `/healthz`, then enable
traffic and restart policies. Clear maintenance only as part of this deliberate
recovery, never as a way to make the timer stop reporting failure.

Destructive production recovery is intentionally NOT implemented. It requires a
separate reviewed outage procedure: fence every writer, preserve a new snapshot
of the current failed state, reconcile post-backup writes, validate the restored
copy, and explicitly switch DB and file sets together. Do not restore over a live
database or mix old files with a newer database.

## Isolated restore rehearsal

`bash scripts/restore_release.sh BACKUP NEW_EMPTY_DIRECTORY` checks backup hashes,
rejects traversal/link archive entries, extracts only uploads/templates into a new
empty directory, and restores to a uniquely named PostgreSQL container. The
container has NO network, published ports, or production volumes. It is retained
on success for inspection; the script prints the exact isolated cleanup command.
On failure only its own isolated container/anonymous volume is removed. This
command never targets a production DB and cannot be used as an in-place rollback.

## Runtime and integration requirements

- Backend UID/GID 10001, read-only root/source, dropped capabilities, no-new-privileges,
  CPU 2, memory 4 GiB, PID 256. `/tmp` is bounded to 256 MiB. This budgets for the
  parent's two parser workers with 1.5 GiB address-space limits; profile RSS under
  representative load before increasing concurrency. DB has a separate 2 GiB cap.
- There are only three writable data mounts. Root is used transiently for data
  ownership with explicit capabilities, never for the serving application.
- Parent model must name the reminder FK
  `fk_candidate_comments_reminder_user_id_users`. Existing unnamed/custom-named
  SQLite FKs and missing indexes are handled by this migration's downgrade.
- Parent owns `/healthz` DB SELECT 1, fail-closed production auth, User.auth_version
  migration after f1c4e92381ad, preserved JWT sid, and rejection of legacy tokens.
- nginx replaces X-Forwarded-For with `$remote_addr`. Uvicorn does not trust proxy
  headers implicitly. The parent's auth layer must define its trusted-proxy policy.
  An external proxy will appear as the peer unless a separately verified nginx
  real-IP allowlist is configured. No TLS certificate/proxy provisioning is inferred
  or added here; inspect the actual external boundary before changes.

## Dependency review

Frontend: Axios 1.21.1, React Router DOM 7.18.6, Vite 6.4.6; compatible PostCSS,
nanoid, and source-map-js transitive updates. No force-audit upgrade or Router 8
migration. The app uses BrowserRouter/Routes/Route/Link/NavLink and navigation
hooks; no loaders/actions, SSR hydration, RSC, or nested splat routes were found.
Router 7 requires Node >=20; CI uses 22 and the existing image uses 20. Maintainer
references: https://github.com/remix-run/react-router/releases/tag/v7.18.6 and
https://github.com/axios/axios/releases/tag/v1.21.1.

Axios browser paths are relevant, but the app does not configure attacker-chosen
cookie names or expose its serializer options. Node HTTP/proxy, follow-redirects,
and Node form-data findings do not describe the browser bundle's execution path.
Router URL handling is browser-relevant, although reviewed destinations are fixed
or generated internal routes; SSR/RSC advisories require absent server features.
Build-tool findings require build/dev inputs or exposed dev servers, not static
nginx serving. These distinctions do not justify keeping affected dependencies.

Python: `requirements-lock.txt` pins the 94-distribution Linux/Python 3.11 audit
snapshot from image c932dc3e9b94, except pip raised from 24.0 to 26.2. Installer
dependencies are also exact; installation disables implicit dependency resolution
and build isolation and runs `pip check`. This is version reproducibility, NOT a
claim of bit-identical rebuilds: wheel hashes, OS packages, and base image digests
are not frozen. Keep the built image IDs for rollback and review new base builds.
`requirements-test.txt` adds pinned pytest/iniconfig/pluggy separately; runtime
does not install it. CI must leave ENABLE_TEST_ENDPOINTS unset for normal pytest.

Remaining audited advisories: python-jose 3.5.0's asymmetric-key/HMAC confusion
prerequisite does not match restricted HS256 with a symmetric random secret;
ecdsa timing-sensitive signing does not match this HS256 path. Neither had an
audit-listed fixed version. Keep algorithm restrictions. Setuptools 79.0.1 is
retained because pyresparser uses legacy pkg_resources; its reported macOS sdist
normalization and Windows legacy wheel installation issues do not execute in this
Linux serving path. Do not build arbitrary untrusted packages in the runtime.
Replacing pyresparser/removing pkg_resources is a separate compatibility change.
