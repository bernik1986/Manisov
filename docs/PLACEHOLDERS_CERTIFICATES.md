# Плейсхолдеры сертификатов (docxtpl)

Сертификаты хранятся в таблице `certificates` с группами:

- `Conventional Certificate` — конвенционные (STCW и смежные)
- `ECDIS Certificate` — типы ECDIS
- `Company Certificate` — компанейские
- `BWTS Certificate` — типы BWTS

Для каждого слота в шаблоне Word: `{{ <prefix>_<field> }}`.

## Поля

- `certificate_number`
- `issue_date`
- `expiry_date`
- `issuing_authority`
- `country_of_issue`

Даты в контексте — `dd-mm-yyyy`.

## Legacy-плейсхолдеры

Некоторые слоты дополнительно заполняют старые имена (см. `legacy_prefixes` в `app/canonical_certificates.py`), например:

| Слот | prefix | legacy |
|------|--------|--------|
| AFF | `aff` | `advanced_fire_fighting_*` |
| PSCRB | `pscrb` | `proficiency_survival_craft_*` |
| MFA | `mfa` | `medical_first_aid_*` |
| SSO | `sso` | `sso_*` |
| BRM / ERM | `brm` / `erm` | `brm_*` / `erm_*` |
| ECDIS | `ecdis` | `ecdis_*` |
| GMDSS | `gmdss` | `gmdss_*` |
| Safety Officer | `safety_off` | `safety_officer_*` |

Полный список prefix для всех 71 слотов генерируется в UI (раздел Certificates → «Плейсхолдеры») и в коде: `canonical_certificate_placeholder_tokens()`.

## Синхронизация

- Backend: `app/canonical_certificates.py`
- Frontend: `app/frontend/src/canonicalCertificates.js` (генерация: `python scripts/gen_canonical_certificates_js.py`)

После изменения Python-спеков перегенерируйте JS.

## Разделы UI

1. **Конвенционные сертификаты** — Basic Safety, PSSR, AFF, PSCRB, MFA, Radar/ARPA, SSO, DSD, Security Awareness, BRM, ERM, ECDIS (общий), High Voltage, HAZMAT, GMDSS, танкерные Oil/Chemical (STCW в сертификатах, не путать с Diplomas → Tanker Diploma).
2. **Specific type of ECDIS** — JRC, Furuno, Transas и др.
3. **Компанейские сертификаты** — FRB, Safety Officer, BWTS (общий), IHM, ISM и др.
4. **Specific type of BWTS** — ERMA, SunRui, Headway, Ecochlor.

Пустые слоты всегда отображаются; при «Редактировать» создаётся строка в БД. Срок действия: Unlimited / +5 лет / ручной ввод (как в Certificates ранее).
