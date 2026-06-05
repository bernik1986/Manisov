# Seamens Data: должность и флот в списке

Документ описывает, **откуда** берутся поля в таблице кандидатов (`/candidates`) и как работают фильтры.

## Должность (колонка и фильтр `position`)

### Источник данных

| Приоритет | Поле | Где в UI |
|-----------|------|----------|
| 1 | `applications.position_applied_for` | Заявка → **Position Applied For** |
| 2 | `applications.rank_applied_for` | Заявка → **Rank Applied For** (если первое пусто) |

Берётся **первая заявка** по `application_id` (самая ранняя).

### Не используется для списка и фильтра

- `candidates.current_rank` (профиль / CV)
- `sea_services.rank_on_vessel` (морской стаж)

Эти поля остаются в карточке и в других сценариях (вложения, ПОДАЧА, поиск по API `/candidates/search` с расширенной логикой — см. код `app/main.py`).

### Нормализация

- В таблице показывается **каноническое** название (Master, Chief Officer, Second Engineer, …).
- Фильтр в выпадающем списке — те же каноны; на backend подставляются синонимы (`Capt`, `2/O`, `C/E`, …) для SQL-поиска по полям заявки.
- Короткие опасные токены (`co`, `ce`, …) в SQL **не** используются, чтобы не было ложных совпадений (например Second **Officer**).

### Если должность в списке «-»

Заполните блок **Заявка / recruitment** в карточке кандидата и нажмите **Сохранить заявку**.

## Флот (колонка и фильтр `fleet`)

| Источник | Поле |
|----------|------|
| Только **последний контракт** (морской стаж) | `sea_services.vessel_type` |

«Последний» = запись с максимальной `sign_on_date` (без даты — в конце), при равенстве — больший `sea_service_id`.

**Не используется:** `applications.proposed_vessel`, `sea_services.vessel_name`, старые строки стажа.

Если `vessel_type` пустой или не распознан как тип флота — в списке **«-»**, фильтр по флоту кандидата не подхватывает.

Нормализация: `app/fleet_normalization.py` (Bulk Carrier, Oil Tanker, …).

## Одноразовая миграция БД (опционально)

Чтобы в PostgreSQL в заявках и профиле лежали уже канонические строки, см. [`normalize_migration_runbook.md`](normalize_migration_runbook.md).

## Тестовые кандидаты для ручной проверки фильтров

**Полные анкеты (50 шт., все секции + сканы):**

```powershell
python scripts/seed_full_demo_candidates.py --seed --count 50
python scripts/seed_full_demo_candidates.py --delete
```

Фамилия: `DemoSeaman001` … `DemoSeaman050`. Поиск: `DemoSeaman`.

**Краткие записи только для фильтров:**

```powershell
python scripts/seed_filter_test_candidates.py --seed --count 50
python scripts/seed_filter_test_candidates.py --delete
```

Фамилия: `FilterTest001` …

## Тесты

| Файл | Что проверяет |
|------|----------------|
| `tests/test_seamens_list_position.py` | Источник должности, фильтр, синонимы |
| `tests/test_position_search_terms_all_ranks.py` | Нет перекрёстных SQL-терминов между должностями |
| `tests/test_rank_normalization_display.py` | Резолв и отображение |
| `tests/test_fleet_normalization.py` | Флот в списке и фильтре |
| `tests/test_seamens_list_fleet.py` | Только последний контракт (`vessel_type`) |
| `e2e/tests/candidates-and-card.spec.cjs` | URL фильтров, колонка после заявки |
