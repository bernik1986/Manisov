# maritime_parser

Каталог `maritime_parser` предназначен для разработки парсера морских документов и подготовки данных для дальнейшей обработки через API и базу данных.

## Структура

- `parser/` — логика извлечения и преобразования данных из входных файлов.
- `models/` — модели данных и схемы хранения.
- `app/rank_normalization.py`, `app/fleet_normalization.py` — канонические должности и типы судов для Seamens Data.
- `tests/` — автотесты для проверки корректности парсинга и преобразований.
- `e2e/tests/` — сквозные UI-тесты (Playwright).
- `docs/SEAMENS_DATA_FILTERS_RU.md` — откуда в списке кандидатов берутся должность и флот.

## Seamens Data: должность в списке

В таблице **Seamens Data** колонка «Должность» и фильтр по должности используют **заявку** (`Position Applied For` / `Rank Applied For`), а не морской стаж и не `current_rank` из профиля. Подробности и тесты — в [`docs/SEAMENS_DATA_FILTERS_RU.md`](docs/SEAMENS_DATA_FILTERS_RU.md).

## E2E (Playwright)

В корне проекта: `package.json` и `playwright.config.cjs`. Тесты поднимают API (`uvicorn` на 8000) и Vite (5173), если порты свободны; иначе переиспользуют уже запущенные сервисы.

```powershell
cd C:\Users\berni\Documents\Parcer
npm install
npm run test:e2e:install
npm run test:e2e
```

Учётные данные по умолчанию в сценариях: `admin` / `admin123`.

## Виртуальное окружение

В каталоге проекта создано виртуальное окружение `.venv`.

Активация в PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Полный сброс БД + новый admin (после деплоя)

Если нужно начать "с нуля" (очистить БД и создать нового администратора), используйте одноразовый скрипт:

```powershell
cd C:\Users\berni\Documents\Parcer
$env:DEFAULT_ADMIN_USERNAME="newadmin"
$env:DEFAULT_ADMIN_PASSWORD="StrongPass123!"
$env:DEFAULT_ADMIN_FULL_NAME="Production Admin"
python scripts/reset_db_and_bootstrap_admin.py --yes
```

Что делает скрипт:
- удаляет все таблицы;
- поднимает схему заново (через Alembic `upgrade head`);
- создает роли и пользователя admin из переменных окружения.

Важно:
- запускать только когда вы точно готовы потерять текущие данные;
- хранить `DEFAULT_ADMIN_PASSWORD` только в защищенных секретах CI/CD/хостинга;
- не включать автосброс на каждый старт приложения.

### Linux one-command helper

```bash
cd /path/to/Parcer
chmod +x scripts/deploy_reset.sh

export DATABASE_URL='postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME'
export DEFAULT_ADMIN_USERNAME='newadmin'
export DEFAULT_ADMIN_PASSWORD='NewStrongPass123!'
export DEFAULT_ADMIN_FULL_NAME='Production Admin'

./scripts/deploy_reset.sh
```

### Auto-reset on app startup (dangerous, but fully "zeroed" deploy)

If you need each start to recreate an empty DB and bootstrap default admin automatically:

```bash
export RESET_DB_ON_START=1
export DEFAULT_ADMIN_USERNAME='admin'
export DEFAULT_ADMIN_PASSWORD='admin123'
export DEFAULT_ADMIN_FULL_NAME='Default Admin'
```

Then start backend as usual (`uvicorn ...` or container startup).  
On startup, app will drop all tables, recreate schema, and create default admin.

Use only for fresh environments/testing; do not enable permanently for production data.

## Требования

Для проекта необходимы следующие пакеты:

- `python-docx`
- `pdfplumber`
- `pandas`
- `openpyxl`
- `sqlalchemy`
- `fastapi`

## Миграции базы данных (Alembic)

В проект добавлен Alembic для управления изменениями схемы БД.

- Конфигурация: `alembic.ini`
- Скрипты миграций: `migrations/`
- Первая миграция текущей схемы: `migrations/versions/0001_initial_current_models.py`

### Применить все миграции

```powershell
alembic upgrade head
```

### Создать новую миграцию после изменения моделей

1. Измените модели в `models/schema.py`.
2. Сгенерируйте ревизию:

```powershell
alembic revision --autogenerate -m "describe schema change"
```

3. Проверьте файл миграции в `migrations/versions/`.
4. Примените миграции:

```powershell
alembic upgrade head
```

### Откат на одну миграцию

```powershell
alembic downgrade -1
```

## Запуск через Docker

В проект добавлены:

- `Dockerfile` — backend (FastAPI + Alembic)
- `app/frontend/Dockerfile` — frontend (Vite)
- `docker-compose.yml` — `db` (PostgreSQL), `backend`, `frontend`

### 1) Собрать и запустить контейнеры

```powershell
docker compose up --build
```

### 2) Открыть приложение

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- PostgreSQL: `localhost:5432` (`maritime/maritime`, DB `maritime`)

### 3) Остановить контейнеры

```powershell
docker compose down
```

### 4) Остановить и удалить volume БД (полный сброс данных)

```powershell
docker compose down -v
```
