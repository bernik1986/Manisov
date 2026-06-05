from __future__ import annotations

import json
from pathlib import Path

from parser.docx_parser import DocxParser


def main() -> None:
    source_path = Path(
        "g:/My Drive/Тестирование Юра/Для работы тестовые файлы/New folder/примеры входящих анкет для теста/333/2E Budurin CR-RT 05A _ SEAMEN'S APPLICATION _ INTERVIEW RECORD.docx"
    )
    output_path = Path("data/budurin_parsed_full.json")
    parsed = DocxParser().parse(source_path)
    output_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
