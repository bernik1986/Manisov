from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

from sqlalchemy import and_, or_

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.db import SessionLocal
from models.schema import Candidate, Certificate, Document, Notification


def _build_document_message(candidate_id: int, document: Document, days_left: int) -> str:
    return (
        f"Candidate #{candidate_id}: document '{document.document_type}' "
        f"(id={document.document_id}) expires in {days_left} days."
    )


def _build_certificate_message(candidate_id: int, certificate: Certificate, days_left: int) -> str:
    return (
        f"Candidate #{candidate_id}: certificate '{certificate.certificate_type}' "
        f"(id={certificate.certificate_id}) expires in {days_left} days."
    )


def run() -> int:
    session = SessionLocal()
    created = 0
    try:
        today = date.today()
        warning_limit = today + timedelta(days=240)

        candidates = (
            session.query(Candidate)
            .filter(
                or_(
                    Candidate.documents.any(
                        and_(
                            Document.date_of_expiry.is_not(None),
                            Document.date_of_expiry >= today,
                            Document.date_of_expiry < warning_limit,
                        )
                    ),
                    Candidate.certificates.any(
                        and_(
                            Certificate.expiry_date.is_not(None),
                            Certificate.expiry_date >= today,
                            Certificate.expiry_date < warning_limit,
                        )
                    ),
                )
            )
            .all()
        )

        for candidate in candidates:
            for document in candidate.documents:
                if not document.date_of_expiry:
                    continue
                days_left = (document.date_of_expiry - today).days
                if not (0 <= days_left < 240):
                    continue
                message = _build_document_message(candidate.candidate_id, document, days_left)
                exists = (
                    session.query(Notification)
                    .filter(
                        Notification.candidate_id == candidate.candidate_id,
                        Notification.document_id == document.document_id,
                        Notification.message == message,
                        Notification.sent.is_(False),
                    )
                    .first()
                )
                if exists:
                    continue
                session.add(
                    Notification(
                        candidate_id=candidate.candidate_id,
                        document_id=document.document_id,
                        message=message,
                        sent=False,
                    )
                )
                created += 1

            for certificate in candidate.certificates:
                if not certificate.expiry_date:
                    continue
                days_left = (certificate.expiry_date - today).days
                if not (0 <= days_left < 240):
                    continue
                message = _build_certificate_message(candidate.candidate_id, certificate, days_left)
                exists = (
                    session.query(Notification)
                    .filter(
                        Notification.candidate_id == candidate.candidate_id,
                        Notification.document_id.is_(None),
                        Notification.message == message,
                        Notification.sent.is_(False),
                    )
                    .first()
                )
                if exists:
                    continue
                session.add(
                    Notification(
                        candidate_id=candidate.candidate_id,
                        document_id=None,
                        message=message,
                        sent=False,
                    )
                )
                created += 1

        session.commit()
        return created
    finally:
        session.close()


if __name__ == "__main__":
    total = run()
    print(f"Notifications created: {total}")
