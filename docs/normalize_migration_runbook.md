# Rank and fleet DB normalization — runbook

Script: [`scripts/normalize_ranks_and_fleet.py`](../scripts/normalize_ranks_and_fleet.py)

## Fields updated

- `candidates.current_rank`, `candidates.certificate_of_competency_rank`
- `applications.position_applied_for`, `applications.rank_applied_for`
- `sea_services.rank_on_vessel`, `sea_services.vessel_type`

После миграции список **Seamens Data** для колонки «Должность» и фильтра `position` по-прежнему читает только поля **заявки** (см. [`SEAMENS_DATA_FILTERS_RU.md`](SEAMENS_DATA_FILTERS_RU.md)).

Not updated: `applications.proposed_vessel`, `sea_services.vessel_name`, etc.

## Commands (Docker Postgres)

```powershell
cd C:\Users\berni\Documents\Parcer
$env:DATABASE_URL = "postgresql+psycopg2://maritime:maritime@localhost:5432/maritime"

# Backup
docker compose exec -T db pg_dump -U maritime maritime > reports/backup_pre_normalize.sql

# Dry-run (no writes)
python scripts/normalize_ranks_and_fleet.py --dry-run --report reports/normalize_dryrun.csv

# Pilot
python scripts/normalize_ranks_and_fleet.py --apply --limit 20

# Full apply
python scripts/normalize_ranks_and_fleet.py --apply --batch-size 200

# Verify idempotency
python scripts/normalize_ranks_and_fleet.py --dry-run --report reports/normalize_post_apply.csv
```

## Dry-run review (local Docker, 2026-05-19)

| Metric | Count |
|--------|------:|
| Candidates | 180 |
| Applications | 29 |
| Sea services | 225 |
| Would update (pre-apply) | 284 |
| Applied | 288 |
| Post-apply dry-run `updated` | 0 (idempotent) |
| Unmapped (remaining) | 20 |

Typical **unmapped** (left unchanged on purpose):

- `OPERATIONAL` in `certificate_of_competency_rank` — not a rank label
- `Fishing vessel`, `Multipurpose` — no canonical fleet yet
- E2E test strings (`E2E-Rank`, `RANK-X`, …)

## Rollback

```powershell
docker compose exec -T db psql -U maritime -d maritime < reports/backup_pre_normalize.sql
```

Or restore from your hosting provider’s snapshot if production is remote.

## Production

Use the same steps against production `DATABASE_URL` only after staging/copy dry-run is acceptable and a fresh backup exists. Archive CSV reports from `reports/`.
