# Плейсхолдеры дипломов (docxtpl)

Дипломы и танкерные дипломы хранятся в таблице `certificates` с группами `Diploma` и `Tanker Diploma`.
В шаблонах Word используйте плейсхолдеры в формате `{{ prefix_field }}`.

## Diplomas

| Слот | Код | prefix |
|------|-----|--------|
| COC (рабочий) | COC | `coc` |
| Endorsement COC | END_COC | `endorsement_coc` |
| COC GMDSS | COC_GMDSS | `coc_gmdss` |
| Endorsement GMDSS | END_GMDSS | `endorsement_gmdss` |
| COC (национальные) | COC_NAT | `coc_national` |
| COP Ship's Welder (FTR) | COP_WELDER | `cop_ships_welder` |
| COP Able Seafarer | COP_AB | `cop_able_seafarer` |
| COP Motorman | COP_MOTO | `cop_motorman` |
| COP Ship's Cook | COP_COOK | `cop_ships_cook` |
| COP Electrician | COP_ELEC | `cop_electrician` |
| COP (прочие) | COP | `cop` |

## Tanker Diploma

| Слот | Код | prefix |
|------|-----|--------|
| COP Basic Oil&Chemical | T_BOC | `cop_basic_oil_chemical` |
| COP Advanced Chemical | T_ACC | `cop_advanced_chemical` |
| COP Advanced Oil | T_AOC | `cop_advanced_oil` |
| COP Basic Gas | T_BG | `cop_basic_gas` |
| COP Advanced Gas | T_AG | `cop_advanced_gas` |

## Поля для каждого слота

Для каждого `prefix` из таблицы выше:

- `{{ prefix_certificate_number }}`
- `{{ prefix_issue_date }}`
- `{{ prefix_expiry_date }}`
- `{{ prefix_issuing_authority }}`
- `{{ prefix_country_of_issue }}`

Слот **COC** (рабочий) дополнительно:

- `{{ coc_competency_rank }}` — звание / capacity с записи COC в Diplomas (поле **COC Rank** в UI)
- при заполнении слота также подставляется `{{ coc_rank }}` (приоритет над полем кандидата **COC Rank**)

Даты в контексте шаблона — строки `dd-mm-yyyy`.

## Обратная совместимость

Слот **COC** (рабочий) заполняет legacy-плейсхолдеры `coc_*` (`coc_document_number`, `coc_issue_date`, …).

Слот **Endorsement COC** — `endorsement_coc_*` и legacy `coc_endorsement_*`.

Слот **COC GMDSS** — `coc_gmdss_*` и legacy `gmdss_*`.

Слот **Endorsement GMDSS** — `endorsement_gmdss_*` и legacy `coc_gmdss_endorsement_*`.

Реализация: `app/canonical_diplomas.py` → `apply_canonical_diploma_placeholders()`.
