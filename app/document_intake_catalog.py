"""CRM catalog and record mappings for document intake."""

from dataclasses import dataclass
from typing import Any

from app.canonical_certificates import ALL_CANONICAL_CERTIFICATE_SPECS, certificate_matches_spec
from app.canonical_diplomas import (
    CANONICAL_DIPLOMA_SPECS,
    CANONICAL_TANKER_DIPLOMA_SPECS,
    diploma_matches_spec,
)
from app.canonical_documents import CANONICAL_DOCUMENT_SPECS, document_matches_spec
from app.canonical_medical import CANONICAL_MEDICAL_SPECS, medical_matches_spec
from app.canonical_visas import CANONICAL_VISA_SPECS, visa_matches_spec
from models.schema import Candidate, Certificate, Document, FlagDocument


DOCUMENT_FIELDS = {
    "number": "document_number", "issue_date": "date_of_issue", "expiry_date": "date_of_expiry",
    "country": "country_of_issue", "authority": "issuing_authority", "place": "place_of_issue",
    "unlimited_validity": "unlimited_validity", "remarks": "remarks",
}
CERTIFICATE_FIELDS = {
    "number": "certificate_number", "issue_date": "date_issued", "expiry_date": "expiry_date",
    "country": "country_of_issue", "authority": "issuing_authority", "code": "certificate_code",
    "unlimited_validity": "unlimited_validity", "remarks": "remarks",
}
FLAG_FIELDS = {
    "number": "doc_number", "issue_date": "date_of_issuance", "expiry_date": "date_of_expiry",
    "country": "flag_country", "rank": "rank", "remarks": "remarks",
}
DOCUMENT_OCR_TITLES = {
    "SB": (
        "seafarer's book", "seafarers book", "seafarer's discharge book",
        "seaman's service book", "seaman service book",
        "\u043c\u043e\u0440\u0435\u0445\u043e\u0434\u043d\u0430\u044f \u043a\u043d\u0438\u0436\u043a\u0430",
        "\u043a\u043d\u0438\u0436\u043a\u0430 \u043c\u043e\u0440\u044f\u043a\u0430",
    ),
    "SID": ("seafarer's identity document", "seafarers identity document",
            "\u043f\u043e\u0441\u0432\u0456\u0434\u0447\u0435\u043d\u043d\u044f \u043e\u0441\u043e\u0431\u0438 \u043c\u043e\u0440\u044f\u043a\u0430"),
    "TP": ("passport for travelling abroad",
           "\u043f\u0430\u0441\u043f\u043e\u0440\u0442 \u0434\u043b\u044f \u0432\u0438\u0457\u0437\u0434\u0443 \u0437\u0430 \u043a\u043e\u0440\u0434\u043e\u043d"),
}


@dataclass(frozen=True)
class IntakeType:
    key: str
    kind: str
    label: str
    model: type
    mapping: dict[str, str]
    identity: dict[str, Any]
    aliases: tuple[str, ...]
    spec: dict | None = None
    matcher: Any = None

    def public(self):
        return {
            "key": self.key, "kind": self.kind, "label": self.label,
            "fields": [*self.mapping, "holder_name"],
            "aliases": list(self.aliases),
        }

    def get_fields(self, row):
        fields = {name: getattr(row, column) for name, column in self.mapping.items()}
        return {key: value for key, value in fields.items() if value is not None}


def _document_type(kind, spec, matcher):
    label = spec["document_type"]
    code = spec["code"]
    return IntakeType(
        f"{kind}:{code}", kind, label, Document, DOCUMENT_FIELDS,
        {"document_type": label, "document_category": code},
        (*spec["match_terms"], *DOCUMENT_OCR_TITLES.get(code, ())), spec, matcher,
    )


def _certificate_type(kind, spec, matcher):
    code = spec["code"]
    label = spec["certificate_type"]
    display_code = spec.get("display_code") or (code if kind == "certificate" else "")
    fields = {**CERTIFICATE_FIELDS, "rank": "competency_rank"} if code in {"COC", "COP"} else CERTIFICATE_FIELDS
    return IntakeType(
        f"{kind}:{code}", kind, "National COC" if code == "COC_NAT" else label, Certificate, fields,
        {
            "certificate_type": label, "certificate_group": spec["certificate_group"],
            "certificate_name_raw": code, "certificate_code": display_code or None,
        },
        tuple(spec["match_terms"]), spec, matcher,
    )


CANONICAL = (
    *(_document_type("visa", spec, visa_matches_spec) for spec in CANONICAL_VISA_SPECS),
    *(_document_type("document", spec, document_matches_spec) for spec in CANONICAL_DOCUMENT_SPECS),
    *(_certificate_type("diploma", spec, diploma_matches_spec)
      for spec in (*CANONICAL_DIPLOMA_SPECS, *CANONICAL_TANKER_DIPLOMA_SPECS)),
    *(_certificate_type("medical", spec, medical_matches_spec) for spec in CANONICAL_MEDICAL_SPECS),
    *(_certificate_type("certificate", spec, certificate_matches_spec) for spec in ALL_CANONICAL_CERTIFICATE_SPECS),
    IntakeType("flag_document:endorsement", "flag_document", "Flag Endorsement", FlagDocument,
               FLAG_FIELDS, {"flag_document_type": "Endorsement"}, ("flag endorsement", "flag state endorsement")),
    IntakeType("flag_document:other", "flag_document", "Flag Document", FlagDocument,
               {**FLAG_FIELDS, "subtype": "flag_document_type"}, {}, ("flag document",)),
)


def _type_for_row(row, catalog):
    candidates = [item for item in catalog.values() if isinstance(row, item.model)]
    if isinstance(row, FlagDocument):
        kind = (row.flag_document_type or "").strip().casefold()
        return catalog["flag_document:endorsement" if kind == "endorsement" else "flag_document:other"]
    if isinstance(row, Document):
        for item in candidates:
            if item.spec and row.document_category == item.spec["code"]:
                return item
        label = (row.document_type or "").strip().casefold()
        for item in candidates:
            if label == item.label.casefold():
                return item
    else:
        for item in candidates:
            if item.spec and row.certificate_name_raw == item.spec["code"]:
                return item
        label = (row.certificate_type or "").strip().casefold()
        exact = [item for item in candidates if item.identity["certificate_type"].casefold() == label]
        if len(exact) == 1:
            return exact[0]
    for item in candidates:
        if item.matcher and item.matcher(row, item.spec):
            return item
    return None


def intake_catalog(candidate: Candidate):
    canonical = {item.key: item for item in CANONICAL}
    catalog = dict(canonical)
    records = []
    for rows, type_field, group_field, id_field in (
        (candidate.documents, "document_type", "document_category", "document_id"),
        (candidate.certificates, "certificate_type", "certificate_group", "certificate_id"),
        (candidate.flag_documents, "flag_document_type", None, "flag_document_id"),
    ):
        for row in rows:
            item = _type_for_row(row, canonical)
            if item is None:
                label = getattr(row, type_field) or ""
                if not label.strip():
                    continue
                group = getattr(row, group_field)
                model = type(row)
                kind = "document" if model is Document else "certificate"
                key = f"{kind}:custom:{group or ''}:{label}"
                mapping = DOCUMENT_FIELDS if model is Document else CERTIFICATE_FIELDS
                item = IntakeType(key, kind, label, model, mapping, {type_field: label, group_field: group}, ())
                catalog[key] = item
            records.append((item, getattr(row, id_field), row))
    return catalog, records
