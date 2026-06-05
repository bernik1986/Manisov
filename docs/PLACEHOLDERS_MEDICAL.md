# Плейсхолдеры мед. документов (docxtpl)

Медицинские документы хранятся в таблице `certificates` с группой `Medical Document`.
В шаблонах Word используйте плейсхолдеры в формате `{{ prefix_field }}`.

## Мед. документы

| Слот | Код | prefix |
|------|-----|--------|
| Covid Certificate | COVID | `covid_certificate` |
| Medical Examination | MED_EXAM | `medical_examination` |
| Hepatitis vaccination | HEP_B | `hepatitis_vaccination` |

## Поля для каждого слота

- `{{ prefix_certificate_number }}`
- `{{ prefix_issue_date }}`
- `{{ prefix_expiry_date }}`
- `{{ prefix_issuing_authority }}`
- `{{ prefix_country_of_issue }}`

Даты в контексте шаблона — строки `dd-mm-yyyy`.

## Обратная совместимость

Слот **Medical Examination** также заполняет legacy-плейсхолдеры `medical_fitness_*`.

Реализация: `app/canonical_medical.py` → `apply_canonical_medical_placeholders()`.
