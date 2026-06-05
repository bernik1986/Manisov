# CrewDeck CRM — подробные требования для тестировщика

Документ фиксирует регрессионные и приемочные требования для полного тестирования системы.

---

## 1. Область тестирования

- Frontend (`app/frontend`) + Backend (`app/main.py`) в связке.
- Роли: `admin`, `recruiter`, `viewer`.
- Потоки: авторизация, кандидаты, карточка, templates manager, users, notifications, logs.
- Окружение: Docker (`db`, `backend`, `frontend`) и локальные автотесты (`pytest`, `playwright`).

---

## 2. Обязательный smoke перед регрессией

1. `docker compose down`
2. `docker compose up -d --build`
3. Проверить доступность:
   - `http://127.0.0.1:5173`
   - `http://127.0.0.1:8000/docs`

Ожидание: все контейнеры в `Up`, БД в `healthy`.

---

## 3. Полный автопрогон

- Backend: `python -m pytest -v --tb=short`
- E2E: `npm run test:e2e -- --reporter=list`

Ожидание:
- `pytest`: все тесты PASS, допустимы только явно помеченные SKIP.
- `playwright`: все сценарии PASS.

---

## 4. Критические функциональные требования (проверять в каждом релизе)

### 4.1 Auth / RBAC

- Вход admin успешен.
- Admin видит `Users` и `Logs` в навигации.
- Viewer не видит admin-ссылки и не получает доступ к `/users` и `/logs`.

### 4.2 User Management

- Создание пользователя работает.
- Смена роли работает для других пользователей.
- Смена статуса `active/inactive` работает.
- Смена пароля работает.
- Удаление пользователя требует confirm.
- Нельзя удалить собственную учётку.
- Для собственного активного admin-аккаунта селект роли disabled.
- Backend не позволяет self-demotion активного admin (даже при наличии другого admin).

### 4.3 Candidate Card (регрессия удаления)

- Для удаления в следующих секциях обязательно появляется confirm:
  - Sea service;
  - Family contacts;
  - K. Flag documents;
  - Candidate.
- Вариант `Cancel` в confirm сохраняет запись (данные не удаляются).

### 4.4 Templates Manager

- Загрузка файлов работает, включая `.DOCX`.
- Удаление файла требует confirm.
- Удаление папки требует confirm.
- Для шаблонов используется только `Download`:
  - кнопка `Download` присутствует;
  - файл скачивается;
  - preview/open потоки отсутствуют.

### 4.5 Notifications / Logs

- Notifications открываются без ошибок.
- Переходы из notifications в карточку кандидата работают.
- Logs открываются и фильтрация работает.

---

## 5. Негативные сценарии

- Невалидный логин/пароль: корректное сообщение об ошибке.
- Попытка вызвать admin endpoints под viewer: запрет доступа.
- Удаление при `Cancel`: состояние неизменно.
- Работа с пустыми списками/таблицами (нет падений UI).

---

## 6. Данные и подготовка

- Тестовые пользователи:
  - `admin/admin123` (или заданные переменными окружения);
  - временные e2e-пользователи создаются/удаляются в тестах.
- Для e2e загрузок использовать test fixtures (`e2e/fixtures`).

---

## 7. Критерии приемки релиза

- Полный автопрогон green (`pytest` + `playwright`).
- Нет регрессий в критических секциях:
  - удаления с confirm;
  - user role/status safety;
  - templates upload/download.
- Нет новых ошибок линтера в изменённых файлах.

---

## 8. Рекомендуемый чеклист ручной проверки (минимум)

1. Login admin → Dashboard.
2. Seamens list: поиск, фильтр должности (совпадает с «Position Applied For» в заявке), фильтр флота, открытие карточки (`docs/SEAMENS_DATA_FILTERS_RU.md`).
3. Candidate card: удалить Sea/Family/Flag с Confirm + Cancel.
4. Templates: upload `.DOCX`, delete with confirm, download file.
5. Users: create user, change role/status/password, delete user.
6. Проверить, что self-admin role select disabled.
7. Logs и Notifications открываются и работают.

---

*Версия требований QA: 2026-05-19 (должность в Seamens Data — из заявки).*
