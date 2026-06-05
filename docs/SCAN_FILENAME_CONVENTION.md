# Имена файлов сканов при загрузке

Все сканы (документы, сертификаты, дипломы, медицина, flag documents и будущие вкладки с тем же механизмом `document:` / `certificate:` / `flag_document:`) при сохранении получают **отображаемое имя** в формате:

```text
{RANK_CODE} {Surname} {SLOT_CODE}.pdf
```

Пример: `CO Chernov AFF.pdf`

- **RANK_CODE** — короткий код должности моряка (см. `app/rank_scan_codes.py`), из `current_rank` кандидата или заявки.
- **Surname** — фамилия кандидата.
- **SLOT_CODE** — значение колонки **Код** в таблице вкладки (для канонических строк — код слота; для сертификатов STCW — `display_code`, например `AFF`, `BST`).

Пробелы между частями сохраняются. Запрещённые символы файловой системы удаляются. Изображения по-прежнему конвертируются в PDF (`app/attachment_convert.py`).

## Коды должностей (примеры)

| Код | Должность |
|-----|-----------|
| MST | Master (Captain) |
| CO | Chief Officer |
| CO Tr | Chief Officer Trainee |
| 2O | Second Officer |
| CE | Chief Engineer |
| AFF | *(не должность — код сертификата в примере)* |

Полный список: `RANK_SCAN_CODES` в `app/rank_scan_codes.py`.

## Код слота (SLOT_CODE)

| Вкладка | Источник поля «Код» |
|---------|---------------------|
| Documents | `document_code` / `document_category` (YF, TP, SB, …) |
| Certificates / Diplomas / Medicine | `certificate_name_raw` (слот) или `certificate_code` / `display_code` (AFF, BST, COVID, …) |
| Flag documents | сокращение `flag_document_type` или страна |

Логика: `app/scan_slot_codes.py`, сборка имени: `app/attachment_naming.py`.

## Расширение

Новая вкладка с каноническими слотами: добавить specs в backend, привязать скан через `description= certificate:{id}` или `document:{id}` — имя подставится автоматически, если в строке заполнены код слота и у кандидата указана должность.
