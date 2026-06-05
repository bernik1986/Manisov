from __future__ import annotations

from pathlib import Path

from models.db import SessionLocal, init_db
from models.schema import Document
from parser.docx_parser import DocxParser


def main() -> None:
    source_path = Path(
        "g:/My Drive/Тестирование Юра/Для работы тестовые файлы/New folder/примеры входящих анкет для теста/333/2E Budurin CR-RT 05A _ SEAMEN'S APPLICATION _ INTERVIEW RECORD.docx"
    )
    parser = DocxParser()
    parsed = parser.parse(source_path)
    print("parsed:", [(d.get("document_type"), d.get("date_of_issue"), d.get("date_of_expiry")) for d in parsed.get("documents", [])])

    init_db()
    session = SessionLocal()
    try:
        candidate = parser._map_and_save_to_db(parsed, session)
        docs = session.query(Document).filter(Document.candidate_id == candidate.candidate_id).all()
        print("saved:", [(d.document_type, d.date_of_issue, d.date_of_expiry) for d in docs])
    finally:
        session.close()


if __name__ == "__main__":
    main()
