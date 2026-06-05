# Калькулятор зарплаты — зафиксированное решение по встраиванию в CRM

**Статус:** реализовано (MVP: матрица в Company, вкладка в карточке, плейсхолдеры `{{salary_*}}`)  
**Дата фиксации:** 2026-06-02  
**Вернуться к задаче:** использовать этот файл + исходное ТЗ (AC1–AC9, формулы, плейсхолдеры)

---

## 1. Цель (кратко)

Раздел **«Калькулятор зарплаты»** в карточке кандидата: расчёт компонентов по **Company + Rank**, ввод **Total Wage** и **Period of Employment**, сохранение результата и подстановка в COE/Contract через плейсхолдеры `{{salary_*}}` при **«Сгенерировать документы»**.

**Формулы:**

- `Fixed Components Total` = Basic Monthly Wage + Monthly Overtime + SEPF + IMTF + Leave + Leave Sub + Various/Extra Overtime  
  (**Overtime Rate** показывается и сохраняется, в сумму не входит.)
- `Owner's Bonus` = Total Wage − Fixed Components Total (только автоматически, read-only).

---

## 2. Куда в UI (решение)

| Решение | Детали |
|--------|--------|
| **Основное место** | Новая **вкладка** в карточке кандидата: после **«Заявка / recruitment»**, до Documents. |
| **Не делать** | Отдельный пункт бокового меню без привязки к кандидату. |
| **Не делать** | Только раздел Company без карточки кандидата. |
| **Опционально позже** | Кнопка на панели + модалка (как «Украинский контракт») — дублирует ту же форму, не заменяет вкладку. |

Порядок работы пользователя: **Company → Rank → Total Wage → Period → (расчёт) → Save → генерация контракта.**

---

## 3. Данные

### 3.1. Справочник (новое)

Таблица матрицы, например `salary_component_templates`:

- `company_id` → FK `companies`
- `rank` (каноническое название: Master, Chief Officer, …)
- фиксированные поля: Basic Monthly Wage, Monthly Overtime, Overtime Rate, SEPF, IMTF, Leave, Leave Sub, Various/Extra Overtime

**Админка:** подраздел в **Company** («Зарплатные ставки» / матрица по рангам) или отдельная страница настроек. Возможен Excel-импорт по аналогии с судами.

API для формы: список рангов по `company_id`; строка матрицы по `company_id` + `rank`.

### 3.2. Сохранённый расчёт (на кандидате)

**MVP:** поле на `candidates`, по аналогии с `ukr_contract_json` — например `salary_calculation_json` (все поля ТЗ + `calculation_date`, `calculated_by`, `company_id`).

**Фаза 2 (при необходимости):** таблица `candidate_salary_calculations` с историей и аудитом.

**Не смешивать** с полями info-list: `desirable_salary_usd`, `rejoin_bonus_usd`, `submission_contract_duration_text` — другой смысл; только подсказки при открытии формы (без автосохранения).

### 3.3. Rank / Company в форме

- **Company** — select из `/companies-manager` (id + name).
- **Rank** — только ранги, для которых есть строка в матрице выбранной компании; при смене Company — сброс Rank и перезагрузка компонентов.
- Маппинг ранга: канонические labels + опциональная подстановка из `current_rank` / заявки (`position_applied_for`) через существующую нормализацию рангов.

---

## 4. Плейсхолдеры и контракт

В `_serialize_candidate_context()` (как для `ukr_contract_json`): развернуть сохранённый расчёт в ключи:

`{{salary_company}}`, `{{salary_rank}}`, `{{salary_total_wage}}`, `{{salary_period_of_employment}}`,  
`{{salary_basic_monthly_wage}}`, `{{salary_monthly_overtime}}`, `{{salary_overtime_rate}}`,  
`{{salary_sepf}}`, `{{salary_imtf}}`, `{{salary_leave}}`, `{{salary_leave_sub}}`,  
`{{salary_various_extra_overtime}}`, `{{salary_fixed_components_total}}`, `{{salary_owners_bonus}}`

Пользовательский путь без новых экранов: **Save в калькуляторе → «Сгенерировать документы» → шаблон COE/Contract** в Templates.

---

## 5. Поведение и кнопки

- При смене **Company** / **Rank** / **Total Wage** — пересчёт (live); кнопки **Calculate** / **Recalculate** — по желанию для v1.
- **Period of Employment** — только сохранение, на Owner's Bonus не влияет.
- **Owner's Bonus** — read-only.
- **Save** — только при валидном расчёте (`Total Wage` ≥ Fixed Components Total, обязательные поля).
- **Reset** — очистка черновика формы.
- Права: **admin + recruiter** редактируют; **viewer** — просмотр сохранённого.

**Валидации (из ТЗ):** Company, Rank, Total Wage обязательны; сообщения на EN как в ТЗ или RU по политике UI.

---

## 6. Связь с существующими разделами

| Раздел | Роль |
|--------|------|
| Seamens Data | вход в карточку |
| Заявка / recruitment | подсказки (ранг, судно) |
| **Калькулятор зарплаты** | новый блок |
| Templates | DOCX с `{{salary_*}}` |
| Company | компании + матрица ставок |
| ПОДАЧА | не пересекается |
| Украинский контракт | параллельный JSON-блок, не объединять |

---

## 7. Этапы реализации (когда вернёмся)

1. Миграция: матрица + (опционально) `salary_calculation_json` на candidates.  
2. API: CRUD матрицы, preview/calculate, save на кандидата.  
3. UI: вкладка в `CandidateDetail.jsx`.  
4. Плейсхолдеры в `_serialize_candidate_context`.  
5. Один тестовый шаблон COE + pytest + E2E smoke.  
6. Документация пользователя (раздел в полном руководстве).

---

## 8. Ссылки в репозитории

- Паттерн сохранения полей контракта: `ukr_contract_json`, `CandidateDetail.jsx`, `ukrContractFields.js`
- Контекст шаблонов: `app/main.py` → `_serialize_candidate_context`
- Компании: `companies` / `CompanyPage`, `/companies-manager`
- Ранги: `app/rank_normalization.py`
- Исходное ТЗ: сообщение заказчика (AC1–AC9, пример Company A / Captain / 3000)

---

*При возврате к задаче: начать с п. 7, этап 1.*
