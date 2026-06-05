from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

from parser.base import BaseParser

_MARIRIME_VESSEL_FLAGS: tuple[str, ...] = (
    "Antigua and Barbuda",
    "Marshall Islands",
    "Saint Vincent and the Grenadines",
    "Cayman Islands",
    "Cook Islands",
    "Sierra Leone",
    "United Kingdom",
    "United States",
    "Hong Kong",
    "Isle of Man",
    "Bahamas",
    "Bermuda",
    "Liberia",
    "Malta",
    "Panama",
    "Cyprus",
    "Gibraltar",
    "Singapore",
    "Norway",
    "Denmark",
    "Netherlands",
    "Greece",
    "Italy",
    "Japan",
    "China",
    "Malaysia",
    "Indonesia",
    "Philippines",
    "Vanuatu",
    "Mongolia",
    "Tanzania",
    "Barbados",
    "Jamaica",
    "India",
    "Russia",
    "Ukraine",
)

_MARIRIME_MAIN_ENGINE_RE = re.compile(
    r"^(MAN[- ]?B&W(?:\s+ME)?|MAN\s+MACS|Mitsubishi(?:\s+RT-FLEX)?|Hyundai\s+HiMSEN|"
    r"General\s+Electric|Wartsila|Yanmar|Matsui|B&W(?:\s+ME)?)(?:\s+(.+))?$",
    re.IGNORECASE,
)


def _split_maririme_vessel_detail_line(line: str) -> dict[str, str | None]:
    """Split Maririme CV experience line: vessel | flag | ME type | owner."""
    text = (line or "").strip()
    if not text:
        return {}

    lower = text.lower()
    flag: str | None = None
    flag_start = -1
    for candidate in sorted(_MARIRIME_VESSEL_FLAGS, key=len, reverse=True):
        pos = lower.find(candidate.lower())
        if pos > 0:
            flag = candidate
            flag_start = pos
            break

    if flag is None or flag_start <= 0:
        return {"vessel_name": text}

    vessel_name = text[:flag_start].strip()
    remainder = text[flag_start + len(flag) :].strip()
    main_engine: str | None = None
    employer: str | None = None
    if remainder:
        em = _MARIRIME_MAIN_ENGINE_RE.match(remainder)
        if em:
            main_engine = em.group(1).strip()
            employer = (em.group(2) or "").strip() or None
        else:
            employer = remainder

    result: dict[str, str | None] = {"vessel_name": vessel_name or None, "flag": flag}
    if main_engine:
        result["main_engine"] = main_engine
    if employer:
        result["employer"] = employer
    return result


class PDFParser(BaseParser):
    """Parser for PDF forms using pdfplumber and pypdfium2."""

    def parse(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        if self.detect_format(path) != ".pdf":
            raise ValueError("PDFParser supports only .pdf files")

        result = self.empty_result()

        # Validate the PDF can be opened/rendered.
        pdf = pdfium.PdfDocument(str(path))
        _ = len(pdf)
        pdf.close()

        page_texts: list[str] = []
        with pdfplumber.open(str(path)) as pdf_doc:
            for page in pdf_doc.pages:
                text = page.extract_text() or ""
                page_texts.append(text)
                self._parse_page(page, result)

        joined_text = "\n".join(page_texts)
        if self._is_maririme_profile(joined_text):
            return self.ensure_result_contract(self._parse_maririme_profile(page_texts))
        if self._is_chandris_crrt_profile(joined_text):
            return self.ensure_result_contract(self._parse_chandris_crrt_profile(page_texts))
        if self._is_crewell_cv_profile(joined_text):
            return self.ensure_result_contract(self._parse_crewell_cv_profile(page_texts))

        return self.ensure_result_contract(result)

    @staticmethod
    def _is_maririme_profile(text: str) -> bool:
        normalized = text.lower()
        return (
            "position desired wage rate employment status" in normalized
            and "experience" in normalized
            and "documents" in normalized
        )

    def _parse_maririme_profile(self, page_texts: list[str]) -> dict[str, Any]:
        result = self.empty_result()
        lines = self._normalize_lines(page_texts)
        if not lines:
            return result

        self._parse_maririme_header(lines, result)
        self._parse_maririme_experience(lines, result)
        self._parse_maririme_documents(lines, result)
        self._parse_maririme_certificates(lines, result)
        return result

    @staticmethod
    def _normalize_lines(page_texts: list[str]) -> list[str]:
        lines: list[str] = []
        for text in page_texts:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("page "):
                    continue
                lines.append(line)
        return lines

    def _parse_maririme_header(self, lines: list[str], result: dict[str, Any]) -> None:
        personal = result["personal_data"]
        applications = result["applications"]

        for line in lines:
            if "@" in line and "email" not in personal:
                personal["email"] = line
                break

        for line in lines:
            m = re.match(r"^([A-Za-z'`\- ]+),\s*(\d{1,2})$", line)
            if m:
                personal["full_name"] = m.group(1).strip()
                personal["age"] = m.group(2).strip()
                parts = [p for p in m.group(1).strip().split(" ") if p]
                if parts:
                    personal["first_name"] = parts[0]
                if len(parts) > 1:
                    personal["surname"] = parts[-1]
                break

        for line in lines:
            if re.match(r"^\d{2}-\d{2}-\d{4}$", line):
                personal["date_of_birth"] = line
                break

        phones: list[str] = []
        for line in lines:
            if re.match(r"^\+\d[\d ]{7,}$", line):
                phones.append(line)
        if phones:
            personal["primary_phone"] = phones[0]
        if len(phones) > 1:
            personal["mobile_phone"] = phones[1]

        for idx, line in enumerate(lines):
            if line == "Position Desired Wage Rate Employment Status" and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                m = re.match(r"^(.*?)\s+\$([\d,]+)\s+(.+)$", next_line)
                if m:
                    rank = m.group(1).strip()
                    salary = m.group(2).strip()
                    personal["position_applied_for"] = rank
                    personal["rank_applied_for"] = rank
                    personal["last_salary_usd"] = salary
                    applications.append({"position_applied_for": rank, "rank_applied_for": rank})
                break

        for idx, line in enumerate(lines):
            if line == "Citizenship Residence Closest Airport" and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                citizenship = next_line.split(" ", 1)[0].strip()
                if citizenship:
                    personal["citizenship"] = citizenship
                    personal["nationality"] = citizenship
                break

        for line in lines:
            if line.lower().startswith("english level:"):
                personal["english_level"] = line.split(":", 1)[1].strip()
                break

    def _parse_maririme_experience(self, lines: list[str], result: dict[str, Any]) -> None:
        sea_service = result["sea_service"]
        exp_re = re.compile(r"^(.*?)\s-\s(.*?)\s(\d{2}\.\d{2}\.\d{4})\s-\s(\d{2}\.\d{2}\.\d{4})")

        i = 0
        while i < len(lines):
            line = lines[i]
            m = exp_re.match(line)
            if not m:
                i += 1
                continue
            item: dict[str, Any] = {
                "rank_on_vessel": m.group(1).strip(),
                "vessel_type": m.group(2).strip(),
                "sign_on_date": m.group(3).strip(),
                "sign_off_date": m.group(4).strip(),
            }

            j = i + 1
            while j < len(lines) and lines[j] == "Vessel Name Vessel flag ME Type Vessel owner":
                if j + 1 < len(lines):
                    for key, value in _split_maririme_vessel_detail_line(lines[j + 1].strip()).items():
                        if value:
                            item[key] = value
                if j + 2 < len(lines) and lines[j + 2] == "Build Year DWT ME Power, kW Agency" and j + 3 < len(lines):
                    build_line = lines[j + 3]
                    bm = re.match(r"^(\d{4})\s+(\d+)(?:\s+([\d,]+))?\s+(.+)$", build_line)
                    if bm:
                        item["dwt"] = bm.group(2).strip()
                        if bm.group(3):
                            item["engine_power"] = bm.group(3).strip()
                        item["manning_agency"] = bm.group(4).strip()
                break

            sea_service.append(item)
            i += 1

    def _parse_maririme_documents(self, lines: list[str], result: dict[str, Any]) -> None:
        documents = result["documents"]
        start = self._find_line_index(lines, "DOCUMENTS")
        if start is None:
            return
        end = self._find_first_index_from(lines, start + 1, {"COC & ENDORSEMENT", "CERTIFICATES", "ADDITIONAL COC & ENDORSEMENT"})
        if end is None:
            end = len(lines)

        for line in lines[start + 1 : end]:
            if not re.match(r"^\d+\s", line):
                continue
            item = self._parse_maririme_doc_like_line(line)
            if item:
                documents.append(item)
            else:
                short = re.sub(r"^\d+\s+", "", line).strip()
                if short and not re.search(r"\d{2}\.\d{2}\.\d{4}", short):
                    documents.append({"document_type": short})

    def _parse_maririme_certificates(self, lines: list[str], result: dict[str, Any]) -> None:
        certificates = result["certificates"]
        for marker in ("COC & ENDORSEMENT", "ADDITIONAL COC & ENDORSEMENT", "CERTIFICATES"):
            start = self._find_line_index(lines, marker)
            if start is None:
                continue
            end = self._find_first_index_from(lines, start + 1, {"CERTIFICATES", "EDUCATION", "PERSONAL INFORMATION"})
            if end is None or end <= start:
                end = len(lines)
            for line in lines[start + 1 : end]:
                if not re.match(r"^\d+\s", line):
                    continue
                item = self._parse_maririme_cert_line(line)
                if item:
                    certificates.append(item)

    @staticmethod
    def _is_chandris_crrt_profile(text: str) -> bool:
        normalized = text.lower()
        return (
            "chandris (hellas) inc." in normalized
            and "cr/rt 05a" in normalized
            and "seamen's application" in normalized
            and "previous sea service" in normalized
        )

    def _parse_chandris_crrt_profile(self, page_texts: list[str]) -> dict[str, Any]:
        result = self.empty_result()
        lines = self._normalize_lines(page_texts)
        if not lines:
            return result

        self._parse_chandris_personal_details(lines, result)
        self._parse_chandris_documents(lines, result)
        self._parse_chandris_certificates(lines, result)
        self._parse_chandris_flag_documents(lines, result)
        self._parse_chandris_sea_service(lines, result)
        return result

    def _parse_chandris_personal_details(self, lines: list[str], result: dict[str, Any]) -> None:
        personal = result["personal_data"]
        applications = result["applications"]
        family_contacts = result["family_contacts"]
        beneficiary_contact: dict[str, Any] | None = None

        for line in lines:
            if line.startswith("Position to Apply for "):
                position = line.split("Position to Apply for", 1)[1].strip()
                if position:
                    personal["position_applied_for"] = position
                    personal["rank_applied_for"] = position
                    applications.append({"position_applied_for": position, "rank_applied_for": position})
                continue

            if line.startswith("Surname "):
                match = re.match(
                    r"^Surname\s+(?P<surname>.+?)\s+First Name\s+(?P<first_name>.+?)\s+Middle Name\s*(?P<middle_name>.*)$",
                    line,
                )
                if match:
                    personal["surname"] = match.group("surname").strip()
                    personal["first_name"] = match.group("first_name").strip()
                    middle_name = match.group("middle_name").strip()
                    if middle_name:
                        personal["middle_name"] = middle_name
                    full_name = " ".join(
                        part
                        for part in (
                            personal.get("first_name"),
                            personal.get("middle_name"),
                            personal.get("surname"),
                        )
                        if part
                    )
                    if full_name:
                        personal["full_name"] = full_name
                continue

            if line.startswith("Date of Birth "):
                match = re.match(
                    r"^Date of Birth\s+(?P<dob>\d{2}\.\d{2}\.\d{4})\s+Place of Birth\s+(?P<pob>.+?)\s+Nationality\s+(?P<nationality>.+)$",
                    line,
                )
                if match:
                    personal["date_of_birth"] = match.group("dob").strip()
                    personal["place_of_birth"] = match.group("pob").strip()
                    nationality = match.group("nationality").strip()
                    personal["nationality"] = nationality
                    personal["citizenship"] = nationality
                continue

            if line.startswith("Address "):
                address = line.split("Address", 1)[1].strip()
                if beneficiary_contact and not beneficiary_contact.get("address") and "Phones" in line:
                    addr_match = re.match(r"^Address\s+(?P<address>.+?)\s+Phones\s+(?P<phones>.+)$", line)
                    if addr_match:
                        beneficiary_address = addr_match.group("address").strip()
                        beneficiary_phone_values = self._extract_phone_values(addr_match.group("phones"))
                        beneficiary_phone = beneficiary_phone_values[0] if beneficiary_phone_values else None
                        beneficiary_contact["address"] = beneficiary_address
                        if beneficiary_phone:
                            beneficiary_contact["phone"] = beneficiary_phone
                        personal["beneficiary_address"] = beneficiary_address
                        if beneficiary_phone:
                            personal["beneficiary_phone"] = beneficiary_phone
                    continue

                if address and "permanent_address" not in personal:
                    personal["permanent_address"] = address
                    personal["current_address"] = address
                    personal["home_address"] = address
                continue

            if line.startswith("Phones /Mob/EMAIL "):
                contact_tail = line.split("Phones /Mob/EMAIL", 1)[1].strip()
                phone_values = self._extract_phone_values(contact_tail)
                email_values = self._extract_email_values(contact_tail)
                if phone_values:
                    personal["primary_phone"] = phone_values[0]
                if len(phone_values) > 1:
                    personal["mobile_phone"] = phone_values[1]
                if email_values:
                    personal["email"] = email_values[0]
                continue

            if line.startswith("Father's Name "):
                match = re.match(r"^Father's Name\s*(?P<father>.*?)\s+Mother's Name\s*(?P<mother>.*)$", line)
                if match:
                    father_name = match.group("father").strip()
                    mother_name = match.group("mother").strip()
                    if father_name:
                        personal["father_name"] = father_name
                    if mother_name:
                        personal["mother_name"] = mother_name
                continue

            if line.startswith("Highest Educational Attainment "):
                match = re.match(
                    r"^Highest Educational Attainment\s+(?P<attainment>.*?)\s+School\s+(?P<school>.*?)\s+Year\s*(?P<year>.*)$",
                    line,
                )
                if match:
                    attainment = self._clean_placeholder_value(match.group("attainment"))
                    school_name = self._clean_placeholder_value(match.group("school"))
                    graduation_year = self._clean_placeholder_value(match.group("year"))
                    if attainment:
                        personal["highest_educational_attainment"] = attainment
                    if school_name:
                        personal["school_name"] = school_name
                    if graduation_year and graduation_year.isdigit():
                        personal["graduation_year"] = int(graduation_year)
                continue

            if line.startswith("Marital Status "):
                match = re.match(
                    r"^Marital Status\s+(?P<status>.+?)\s+Children:\s*(?P<children>\d+)?(?:\s+No\. of Children Below 18 yrs\. Old\s*(?P<under18>\d+)?)?$",
                    line,
                )
                if match:
                    marital_status = match.group("status").strip()
                    if marital_status:
                        personal["marital_status"] = marital_status
                    children = match.group("children")
                    under_18 = match.group("under18")
                    if children:
                        personal["number_of_children"] = int(children)
                    if under_18:
                        personal["children_under_18_count"] = int(under_18)
                continue

            if line.startswith("Name of Beneficiary "):
                match = re.match(r"^Name of Beneficiary\s+(?P<full_name>.+?)\s+Relation\s+(?P<relationship>.+)$", line)
                if match:
                    full_name = match.group("full_name").strip()
                    relationship = match.group("relationship").strip()
                    personal["beneficiary_full_name"] = full_name
                    personal["beneficiary_relationship"] = relationship
                    beneficiary_contact = {
                        "contact_type": "beneficiary",
                        "full_name": full_name,
                        "relationship_to_candidate": relationship,
                        "beneficiary_full_name": full_name,
                        "beneficiary_relationship": relationship,
                    }
                continue

            if line.startswith("English Ability "):
                match = re.match(
                    r"^English Ability\s+(?P<english>.+?)\s+Certificate\s+(?P<certificate>.*?)\s+Other Language\s+(?P<other_language>.*)$",
                    line,
                )
                if match:
                    english_level = self._clean_placeholder_value(match.group("english"))
                    english_certificate = self._clean_placeholder_value(match.group("certificate"))
                    other_languages = self._clean_placeholder_value(match.group("other_language"))
                    if english_level:
                        personal["english_level"] = english_level
                    if english_certificate:
                        personal["english_certificate"] = english_certificate
                    if other_languages:
                        personal["other_languages"] = other_languages
                continue

            if line.startswith("Distinctive Marks"):
                match = re.match(
                    r"^Distinctive Marks\s*(?P<marks>.*?)\s+Height \(m\)\s+(?P<height>[\d.]+)\s+Weight \(kg\)\s+(?P<weight>[\d.]+)$",
                    line,
                )
                if match:
                    distinctive_marks = self._clean_placeholder_value(match.group("marks"))
                    raw_height = match.group("height").strip()
                    raw_weight = match.group("weight").strip()
                    if distinctive_marks:
                        personal["distinctive_marks"] = distinctive_marks
                    if raw_height:
                        try:
                            height_value = float(raw_height)
                            if height_value > 10:
                                personal["height_cm"] = height_value
                                personal["height_m"] = round(height_value / 100, 2)
                            else:
                                personal["height_m"] = height_value
                                personal["height_cm"] = round(height_value * 100, 2)
                        except ValueError:
                            pass
                    if raw_weight:
                        try:
                            personal["weight_kg"] = float(raw_weight)
                        except ValueError:
                            pass

        if beneficiary_contact and beneficiary_contact.get("full_name"):
            family_contacts.append(beneficiary_contact)

    def _parse_chandris_documents(self, lines: list[str], result: dict[str, Any]) -> None:
        personal = result["personal_data"]
        documents = result["documents"]
        patterns = [
            (
                "Seaman's Book",
                r"^Seaman's Book\. No\.\s+(?P<number>.+?)\s+Date of Issue\s+(?P<issue>\d{2}\.\d{2}\.\d{4}|-)\s+Date of Validity(?:\s+(?P<expiry>Unlimited|-|\d{2}\.\d{2}\.\d{4}))?\s+Place of Issue\s*(?P<place>.*)$",
            ),
            (
                "Passport",
                r"^Passport No\.\s+(?P<number>.+?)\s+Date of Issue\s+(?P<issue>\d{2}\.\d{2}\.\d{4}|-)\s+Date of Validity\s+(?P<expiry>Unlimited|-|\d{2}\.\d{2}\.\d{4})\s+Place of Issue\s*(?P<place>.*)$",
            ),
            (
                "USA Visa",
                r"^USA Visa No\.\s+(?P<number>.+?)\s+Date of Issue\s+(?P<issue>\d{2}\.\d{2}\.\d{4}|-)\s+Date of Validity\s+(?P<expiry>Unlimited|-|\d{2}\.\d{2}\.\d{4})\s+Place of Issue\s*(?P<place>.*)$",
            ),
        ]

        seen_document_types: set[str] = set()
        for idx, line in enumerate(lines):
            candidate_chunks = [line]
            if idx + 1 < len(lines):
                candidate_chunks.append(f"{line} {lines[idx + 1]}")
            for document_type, pattern in patterns:
                if document_type in seen_document_types:
                    continue
                for chunk in candidate_chunks:
                    normalized_chunk = re.sub(r"\s+", " ", chunk).strip()
                    match = re.match(pattern, normalized_chunk)
                    if not match:
                        continue
                    place_of_issue = self._clean_placeholder_value(match.group("place"))
                    if place_of_issue and place_of_issue.startswith("(Renewing) "):
                        place_of_issue = place_of_issue.replace("(Renewing) ", "", 1).strip()
                    if place_of_issue and place_of_issue.startswith("- Yellow Fever"):
                        place_of_issue = None
                    item = {
                        "document_type": document_type,
                        "document_number": self._clean_placeholder_value(match.group("number")),
                        "date_of_issue": self._clean_placeholder_value(match.group("issue")),
                        "date_of_expiry": self._clean_placeholder_value(match.group("expiry")),
                        "place_of_issue": place_of_issue,
                        "country_of_issue": place_of_issue,
                    }
                    if not any(
                        (
                            item["document_number"],
                            item["date_of_issue"],
                            item["date_of_expiry"],
                        )
                    ):
                        continue
                    documents.append(item)
                    seen_document_types.add(document_type)

                    if document_type == "Seaman's Book":
                        personal["seaman_book_number"] = item["document_number"]
                    elif document_type == "Passport":
                        personal["passport_number"] = item["document_number"]
                        personal["passport_issue_date"] = item["date_of_issue"]
                        personal["passport_expiry_date"] = item["date_of_expiry"]
                        personal["passport_place_of_issue"] = item["place_of_issue"]
                    elif document_type == "USA Visa":
                        personal["usa_visa_number"] = item["document_number"]
                        personal["usa_visa_issue_date"] = item["date_of_issue"]
                        personal["usa_visa_expiry_date"] = item["date_of_expiry"]
                        personal["usa_visa_place_of_issue"] = item["place_of_issue"]
                    break

    def _parse_chandris_certificates(self, lines: list[str], result: dict[str, Any]) -> None:
        personal = result["personal_data"]
        certificates = result["certificates"]

        for idx, line in enumerate(lines):
            if "Yellow Fever" not in line:
                continue
            chunk = " ".join(lines[idx : min(idx + 3, len(lines))])
            chunk = chunk.replace("Vaccination", " ").replace("  ", " ")
            match = re.search(
                r"Date of Issue\s+(?P<issue>\d{2}\.\d{2}\.\d{4}|-)\s+Date of Validity\s+(?P<expiry>Unlimited|-|\d{2}\.\d{2}\.\d{4})\s+Place of Issue\s+(?P<place>.+)$",
                chunk,
            )
            if match:
                expiry = self._clean_placeholder_value(match.group("expiry"))
                certificates.append(
                    {
                        "certificate_type": "Yellow Fever Vaccination",
                        "date_issued": self._clean_placeholder_value(match.group("issue")),
                        "expiry_date": expiry,
                        "unlimited_validity": match.group("expiry").strip().lower() == "unlimited",
                        "country_of_issue": match.group("place").strip(),
                    }
                )
                personal["yellow_fever_issue_date"] = self._clean_placeholder_value(match.group("issue"))
                personal["yellow_fever_expiry_date"] = expiry
                personal["yellow_fever_unlimited"] = match.group("expiry").strip().lower() == "unlimited"
                break

        for idx, line in enumerate(lines):
            if "Cert. of Competency Rank" not in line:
                continue
            match = re.search(
                r"Cert\. of Competency Rank\s*(?P<rank>.*?)\s+Date of Issue\s+(?P<issue>\d{2}\.\d{2}\.\d{4})\s+Date of Validity\s+(?P<expiry>\d{2}\.\d{2}\.\d{4}|-)",
                line,
            )
            if not match:
                continue
            inline_rank = match.group("rank").strip()
            previous_line = lines[idx - 1].strip() if idx > 0 else ""
            next_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            cert_number = None
            for candidate_line in lines[idx + 1 : min(idx + 4, len(lines))]:
                number_match = re.match(r"^(?:Ceritificate|Certificate) No\s+(.+)$", candidate_line)
                if number_match:
                    cert_number = number_match.group(1).strip()
                    break

            rank_parts: list[str] = []
            if previous_line and self._looks_like_chandris_rank_fragment(previous_line):
                rank_parts.append(previous_line)
            if inline_rank:
                rank_parts.append(inline_rank)
            if next_line and self._looks_like_chandris_rank_fragment(next_line):
                rank_parts.append(next_line)
            competency_rank = " ".join(part for part in rank_parts if part).replace("- ", "-").strip(" -")

            certificates.append(
                {
                    "certificate_type": "Certificate of Competency",
                    "certificate_name_raw": competency_rank or None,
                    "certificate_number": cert_number,
                    "competency_rank": competency_rank or None,
                    "date_issued": match.group("issue").strip(),
                    "expiry_date": self._clean_placeholder_value(match.group("expiry")),
                    "remarks": competency_rank or None,
                }
            )
            if competency_rank:
                personal["certificate_of_competency_rank"] = competency_rank
            if cert_number:
                personal["certificate_of_competency_number"] = cert_number
            break

    def _parse_chandris_flag_documents(self, lines: list[str], result: dict[str, Any]) -> None:
        start = next((idx for idx, line in enumerate(lines) if "D. FLAG DOCUMENTS" in line), None)
        if start is None:
            return
        end = next((idx for idx in range(start + 1, len(lines)) if lines[idx].startswith("E. SECURITY")), len(lines))
        for line in lines[start + 1 : end]:
            if not line or line.startswith("FLAG "):
                continue
            match = re.match(
                r"^(?P<country>[A-Za-z]+)\s+(?P<doc_type>[A-Za-z ]+?)\s+(?P<number>[A-Z0-9/\-]+)\s+(?P<issue>\d{2}\.\d{2}\.\d{4})\s+(?P<expiry>\d{2}\.\d{2}\.\d{4}|-)$",
                line,
            )
            if not match:
                continue
            result["flag_documents"].append(
                {
                    "flag_country": match.group("country").strip(),
                    "flag_document_type": match.group("doc_type").strip(),
                    "doc_number": match.group("number").strip(),
                    "date_of_issuance": match.group("issue").strip(),
                    "date_of_expiry": self._clean_placeholder_value(match.group("expiry")),
                }
            )

    def _parse_chandris_sea_service(self, lines: list[str], result: dict[str, Any]) -> None:
        start = next((idx for idx, line in enumerate(lines) if "B(i). PREVIOUS SEA SERVICE" in line), None)
        if start is None:
            return
        end = next(
            (idx for idx in range(start + 1, len(lines)) if "SHIPYARD EXPERIENCE" in lines[idx]),
            len(lines),
        )
        service_lines = [
            line
            for line in lines[start + 1 : end]
            if line
            and "CHANDRIS (HELLAS) INC." not in line
            and "SEAMEN'S APPLICATION AND DOC:" not in line
            and "INTERVIEW RECORD" not in line
            and "VESSEL TYPE GRT" not in line
            and "(dd/mm/yy)" not in line
        ]
        for idx, line in enumerate(service_lines):
            if not re.search(r"\d{2}\.\d{2}\.\d{4}\s+\d{2}\.\d{2}\.\d{4}", line):
                continue
            previous_two = service_lines[idx - 2] if idx >= 2 else ""
            previous_one = service_lines[idx - 1] if idx >= 1 else ""
            next_one = service_lines[idx + 1] if idx + 1 < len(service_lines) else ""
            next_two = service_lines[idx + 2] if idx + 2 < len(service_lines) else ""
            item = self._parse_chandris_sea_service_row(line, previous_two, previous_one, next_one, next_two)
            if item:
                result["sea_service"].append(item)

    def _parse_chandris_sea_service_row(
        self,
        row_line: str,
        previous_two: str,
        previous_one: str,
        next_one: str,
        next_two: str,
    ) -> dict[str, Any] | None:
        cleaned_row = re.sub(r"Page \d+ of \d+", "", row_line).strip()
        date_match = re.search(r"(?P<sign_on>\d{2}\.\d{2}\.\d{4})\s+(?P<sign_off>\d{2}\.\d{2}\.\d{4})", cleaned_row)
        if not date_match:
            return None

        prefix = cleaned_row[: date_match.start()].strip()
        suffix = cleaned_row[date_match.end() :].strip()
        rank = self._extract_chandris_rank(prefix)
        if rank:
            prefix = prefix[: prefix.rfind(rank)].strip()

        vessel_name, grt, main_engine, engine_power = self._parse_chandris_service_prefix(prefix)
        employer_suffix, discharge_reason = self._split_chandris_employer_and_discharge(suffix)
        vessel_type = self._extract_chandris_vessel_type(previous_one, next_one)
        employer = self._extract_chandris_employer(previous_two, employer_suffix, next_two)

        if not main_engine:
            main_engine = self._extract_chandris_engine(previous_one, next_one)

        flag = self._extract_chandris_flag(previous_one, next_one, previous_two)
        if not engine_power and main_engine:
            split_engine, split_power = self._split_engine_power_tokens(main_engine)
            main_engine, engine_power = split_engine, split_power or engine_power

        if not vessel_name:
            return None

        item: dict[str, Any] = {
            "vessel_name": vessel_name,
            "vessel_type": vessel_type,
            "flag": flag,
            "grt": grt,
            "main_engine": main_engine,
            "engine_power": engine_power,
            "rank_on_vessel": rank,
            "sign_on_date": date_match.group("sign_on"),
            "sign_off_date": date_match.group("sign_off"),
            "employer": employer,
            "remarks": discharge_reason,
        }
        return {key: value for key, value in item.items() if value not in (None, "")}

    def _extract_chandris_rank(self, prefix: str) -> str | None:
        known_ranks = [
            "Chief Officer",
            "Second Officer",
            "Third Officer",
            "Chief Engineer",
            "Second Engineer",
            "Third Engineer",
            "Fourth Engineer",
            "Electro Technical Officer",
            "Electro-Technical Officer",
            "First-class electro-technical officer",
            "Electrician",
            "Master",
            "ETO",
            "2O",
            "3O",
            "C/O",
            "2/E",
            "3/E",
            "4/E",
            "AB",
            "OS",
            "Bosun",
        ]
        for rank in sorted(known_ranks, key=len, reverse=True):
            if prefix.endswith(rank):
                return rank
        return None

    def _parse_chandris_service_prefix(self, prefix: str) -> tuple[str | None, str | None, str | None, str | None]:
        tokens = prefix.split()
        if not tokens:
            return None, None, None, None

        first_meta_idx = next((idx for idx, token in enumerate(tokens) if any(char.isdigit() for char in token)), len(tokens))
        vessel_name = " ".join(tokens[:first_meta_idx]).strip() or None
        meta_tokens = tokens[first_meta_idx:]
        if not meta_tokens:
            return vessel_name, None, None, None

        numeric_or_engine_tokens: list[str] = []
        for token in meta_tokens:
            if any(char.isdigit() for char in token) or "-" in token:
                numeric_or_engine_tokens.append(token)

        grt = numeric_or_engine_tokens[0] if numeric_or_engine_tokens else None
        main_engine = None
        engine_power = None
        if len(numeric_or_engine_tokens) == 2:
            if numeric_or_engine_tokens[1].isdigit():
                engine_power = numeric_or_engine_tokens[1]
            else:
                main_engine = numeric_or_engine_tokens[1]
        elif len(numeric_or_engine_tokens) >= 3:
            if numeric_or_engine_tokens[-1].isdigit():
                engine_power = numeric_or_engine_tokens[-1]
                if len(numeric_or_engine_tokens) > 2:
                    main_engine = " ".join(numeric_or_engine_tokens[1:-1]).strip() or None
            else:
                main_engine = " ".join(numeric_or_engine_tokens[1:]).strip() or None

        return vessel_name, grt, main_engine, engine_power

    def _extract_chandris_flag(self, previous_one: str, next_one: str, previous_two: str) -> str | None:
        for fragment in (previous_one, next_one, previous_two):
            if not fragment:
                continue
            low = fragment.lower()
            for name in sorted(_MARIRIME_VESSEL_FLAGS, key=len, reverse=True):
                if name.lower() in low:
                    return name
        return None

    @staticmethod
    def _split_engine_power_tokens(main_engine: str) -> tuple[str | None, str | None]:
        text = (main_engine or "").strip()
        if not text:
            return None, None
        match = re.match(
            r"^(?P<engine>.+?)\s+(?P<power>\d[\d.,]*\s*(?:kw|bhp|hp|ps))\s*$",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group("engine").strip() or None, match.group("power").strip() or None
        tokens = text.split()
        if len(tokens) >= 2 and re.fullmatch(r"\d[\d.,]*(?:kw|bhp|hp|ps)", tokens[-1], flags=re.IGNORECASE):
            return " ".join(tokens[:-1]).strip() or None, tokens[-1]
        return text, None

    def _extract_chandris_vessel_type(self, previous_one: str, next_one: str) -> str | None:
        combined = f"{previous_one} {next_one}".lower()
        if "crude oil" in combined and "tanker" in combined:
            return "Crude Oil Tanker"
        if "chemical" in combined and "tanker" in combined:
            return "Chemical Tanker"
        if "oil" in combined and "tanker" in combined:
            return "Oil Tanker"
        if "bulk" in combined and "carrier" in combined:
            return "Bulk Carrier"
        if "tanker" in combined:
            return "Tanker"
        if "container" in combined:
            return "Container"
        return None

    def _extract_chandris_engine(self, previous_one: str, next_one: str) -> str | None:
        engine_tokens: list[str] = []
        for fragment in (previous_one, next_one):
            for token in fragment.split():
                if token.upper() in {"MAN-B&W", "B&W", "WARTSILA", "SULZER"} or (
                    any(char.isdigit() for char in token) and any(char.isalpha() for char in token)
                ):
                    engine_tokens.append(token)
        if not engine_tokens:
            return None
        return " ".join(dict.fromkeys(engine_tokens))

    def _split_chandris_employer_and_discharge(self, suffix: str) -> tuple[str | None, str | None]:
        cleaned = re.sub(r"Page \d+ of \d+", "", suffix).strip(" /\\")
        if not cleaned:
            return None, None
        match = re.search(
            r"(?P<employer>.*?)(?:[/\\\s]+)?(?P<reason>EOC|Transfer|Promotion|Relief|Dismissal|Sign\s*Off)$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            employer = match.group("employer").strip(" /\\")
            reason = match.group("reason").replace("  ", " ").strip()
            return employer or None, reason.upper() if reason.upper() == "EOC" else reason
        if re.fullmatch(r"\d+\s*(?:crane|cranes|grab|grabs)\b.*", cleaned, flags=re.IGNORECASE):
            return None, None
        return cleaned or None, None

    def _extract_chandris_employer(self, previous_two: str, employer_suffix: str | None, next_two: str) -> str | None:
        fragments: list[str] = []
        for fragment in (previous_two, employer_suffix or "", next_two):
            cleaned = re.sub(r"Page \d+ of \d+", "", fragment).strip(" /\\")
            if not cleaned or self._looks_like_chandris_noise(cleaned):
                continue
            if not re.search(r"[A-Za-z]", cleaned):
                continue
            fragments.append(cleaned)
        if not fragments:
            return None
        return " ".join(dict.fromkeys(fragments))

    @staticmethod
    def _looks_like_chandris_rank_fragment(value: str) -> bool:
        if not value:
            return False
        lowered = value.lower()
        return not any(
            marker in lowered
            for marker in (
                "yellow fever",
                "vaccination",
                "date of issue",
                "date of validity",
                "place of issue",
                "english ability",
                "certificate no",
                "ceritificate no",
                "passport no",
                "usa visa no",
                "seaman's book",
                "b(i). previous sea service",
            )
        )

    @staticmethod
    def _looks_like_chandris_noise(value: str) -> bool:
        normalized = value.lower()
        if not normalized:
            return True
        noise_markers = {
            "crude oil",
            "tanker",
            "page 1 of 5",
            "page 2 of 5",
            "page 3 of 5",
            "page 4 of 5",
            "page 5 of 5",
            "page 6 of 5",
        }
        return normalized in noise_markers

    @staticmethod
    def _extract_phone_values(text: str) -> list[str]:
        values = re.findall(r"(?<!\d)\+?\d[\d ]{5,}(?!\d)", text)
        cleaned: list[str] = []
        for value in values:
            normalized = re.sub(r"\s+", "", value).strip()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    @staticmethod
    def _extract_email_values(text: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"[\w.\-+]+@[\w.\-]+\.\w+", text)))

    @staticmethod
    def _clean_placeholder_value(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned in {"", "-", "--", "—"}:
            return None
        return cleaned

    def _parse_maririme_doc_like_line(self, line: str) -> dict[str, Any] | None:
        date_matches = re.findall(r"\d{2}\.\d{2}\.\d{4}", line)
        if len(date_matches) < 2:
            return None
        issue_date, expiry_date = date_matches[0], date_matches[1]
        prefix = line.split(issue_date, 1)[0]
        prefix = re.sub(r"^\d+\s+", "", prefix).strip()
        tokens = prefix.split()
        if len(tokens) < 3:
            return None
        doc_number = " ".join(tokens[-2:]).strip()
        document_type = " ".join(tokens[:-2]).strip()
        if not document_type:
            return None
        return {
            "document_type": document_type,
            "document_number": doc_number,
            "date_of_issue": issue_date,
            "date_of_expiry": expiry_date,
        }

    @staticmethod
    def _is_crewell_cv_profile(text: str) -> bool:
        normalized = text.lower()
        return "cv" in normalized and "main info" in normalized and "passports / smbk" in normalized

    def _parse_crewell_cv_profile(self, page_texts: list[str]) -> dict[str, Any]:
        result = self.empty_result()
        lines = self._normalize_lines(page_texts)
        if not lines:
            return result

        personal = result["personal_data"]
        applications = result["applications"]

        for line in lines:
            if line.startswith("Name / Surname:"):
                full = line.split(":", 1)[1].strip()
                personal["full_name"] = full
                parts = [p for p in full.split(" ") if p]
                if parts:
                    personal["first_name"] = parts[0]
                if len(parts) > 1:
                    personal["surname"] = parts[-1]
            if line.startswith("Position applied for:"):
                rank = line.split(":", 1)[1].strip()
                if "Desired Vessel Type:" in rank:
                    rank = rank.split("Desired Vessel Type:")[0].strip()
                personal["position_applied_for"] = rank
                personal["rank_applied_for"] = rank
                applications.append({"position_applied_for": rank, "rank_applied_for": rank})
            if "Birthday / Place of birth:" in line:
                rest = line.split("Birthday / Place of birth:", 1)[1].strip()
                m = re.match(r"(\d{2}\.\d{2}\.\d{4})\s+(.+)$", rest)
                if m:
                    personal["date_of_birth"] = m.group(1).strip()
                    personal["place_of_birth"] = m.group(2).strip()
            if line.startswith("Phones:"):
                phone = line.split("Phones:", 1)[1].strip()
                if phone:
                    personal["primary_phone"] = phone
            if line.startswith("E-mail:"):
                personal["email"] = line.split("E-mail:", 1)[1].strip().split(" ")[0]
            if line.startswith("English level:"):
                personal["english_level"] = line.split("English level:", 1)[1].strip().split("Closest airport:")[0].strip()
            if "Citizenship:" in line:
                citizenship = line.split("Citizenship:", 1)[1].strip().split(" ")[0]
                personal["citizenship"] = citizenship
                personal["nationality"] = citizenship

        self._parse_crewell_documents(lines, result)
        self._parse_crewell_certificates(lines, result)
        self._parse_crewell_sea_service(lines, result)
        return result

    def _parse_crewell_documents(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Passports / Smbk")
        end = self._find_line_index(lines, "Diplomas")
        if start is None or end is None or end <= start:
            return
        for line in lines[start + 1 : end]:
            if line.startswith("Title of document") or line.startswith("Rank"):
                continue
            m = re.match(r"(.+?)\s+([A-Z0-9/\-]+)\s+(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+(\d{2}\.\d{2}\.\d{4})$", line)
            if m:
                result["documents"].append(
                    {
                        "document_type": m.group(1).strip(),
                        "document_number": m.group(2).strip(),
                        "date_of_issue": m.group(3).strip(),
                        "date_of_expiry": m.group(5).strip(),
                        "country_of_issue": m.group(4).strip(),
                    }
                )

    def _parse_crewell_certificates(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Certificates")
        if start is None:
            return
        end = self._find_first_index_from(lines, start + 1, {"Medical certificates", "Sea service (last 5 years)", "Biometrics"})
        if end is None:
            end = len(lines)
        for line in lines[start + 1 : end]:
            if line.startswith("Title of document"):
                continue
            m = re.match(r"(.+?)\s+([A-Z0-9/\-]+)\s+(\d{2}\.\d{2}\.\d{4})\s+([A-Za-z]+)\s+(\d{2}\.\d{2}\.\d{4})$", line)
            if m:
                result["certificates"].append(
                    {
                        "certificate_type": m.group(1).strip(),
                        "certificate_number": m.group(2).strip(),
                        "date_issued": m.group(3).strip(),
                        "country_of_issue": m.group(4).strip(),
                        "expiry_date": m.group(5).strip(),
                    }
                )

    def _parse_crewell_sea_service(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Sea service (last 5 years)")
        if start is None:
            return
        end = self._find_first_index_from(lines, start + 1, {"Biometrics", "Additional info", "Next of Kin"})
        if end is None:
            end = len(lines)
        date_re = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})")
        for line in lines[start + 1 : end]:
            m = date_re.search(line)
            if not m:
                continue
            prefix = line[: m.start()].strip()
            item: dict[str, Any] = {"sign_on_date": m.group(1), "sign_off_date": m.group(2)}
            if "/" in prefix:
                vessel = prefix.split("/", 1)[0].strip()
                if vessel:
                    item["vessel_name"] = vessel
            if "Chief Officer" in line:
                item["rank_on_vessel"] = "Chief Officer"
            elif "Master" in line:
                item["rank_on_vessel"] = "Master"
            result["sea_service"].append(item)

    def _parse_maririme_cert_line(self, line: str) -> dict[str, Any] | None:
        expiry = "No expiry" if "No expiry" in line else None
        dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", line)
        if not dates and not expiry:
            return None
        issue_date = dates[0] if dates else None
        expiry_date = dates[1] if len(dates) > 1 else expiry
        body = re.sub(r"^\d+\s+", "", line).strip()
        if issue_date:
            body = body.split(issue_date, 1)[0].strip()
        tokens = body.split()
        if len(tokens) < 2:
            return None
        certificate_number = tokens[-1]
        certificate_type = " ".join(tokens[:-1]).strip()
        item: dict[str, Any] = {
            "certificate_type": certificate_type,
            "certificate_number": certificate_number,
        }
        if issue_date:
            item["date_issued"] = issue_date
        if expiry_date:
            item["expiry_date"] = expiry_date
        return item

    @staticmethod
    def _find_line_index(lines: list[str], target: str) -> int | None:
        for idx, line in enumerate(lines):
            if line == target:
                return idx
        return None

    @staticmethod
    def _find_first_index_from(lines: list[str], start: int, targets: set[str]) -> int | None:
        for idx in range(start, len(lines)):
            if lines[idx] in targets:
                return idx
        return None

    def _parse_page(self, page: pdfplumber.page.Page, result: dict[str, Any]) -> None:
        text = page.extract_text() or ""
        for line in text.splitlines():
            self._try_parse_key_value_line(line, result)

        tables = page.extract_tables() or []
        for table in tables:
            self._parse_table(table, result)

    def _try_parse_key_value_line(self, line: str, result: dict[str, Any]) -> None:
        if ":" not in line:
            return
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return

        canonical = self.map_to_canonical_field(key)
        if canonical:
            result["personal_data"][canonical] = value

    def _parse_table(self, table: list[list[str | None]], result: dict[str, Any]) -> None:
        if not table or not table[0]:
            return

        raw_headers = [str(col or "").strip() for col in table[0]]
        canonical_headers = [self.map_to_canonical_field(h) if h else None for h in raw_headers]
        if not any(canonical_headers):
            return

        for row in table[1:]:
            values = [str(cell or "").strip() for cell in row]
            if not any(values):
                continue

            item: dict[str, Any] = {}
            for idx, value in enumerate(values):
                if not value:
                    continue
                canonical = canonical_headers[idx] if idx < len(canonical_headers) else None
                if canonical:
                    item[canonical] = value

            if not item:
                continue
            self._append_by_section(item, result)

    def _append_by_section(self, item: dict[str, Any], result: dict[str, Any]) -> None:
        keys = set(item.keys())
        if {"document_type", "document_number"} & keys:
            result["documents"].append(item)
        elif {"certificate_type", "certificate_number"} & keys:
            result["certificates"].append(item)
        elif {"vessel_name", "rank_on_vessel", "sign_on_date", "sign_off_date"} & keys:
            result["sea_service"].append(item)
        elif {"position_applied_for", "rank_applied_for", "date_applied"} & keys:
            result["applications"].append(item)
        else:
            result["personal_data"].update(item)
