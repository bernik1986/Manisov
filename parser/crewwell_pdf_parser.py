from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium

from parser.base import BaseParser


class CrewwellPDFParser(BaseParser):
    """Parser for Crewwell CV-style PDF forms."""

    def parse(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        if self.detect_format(path) != ".pdf":
            raise ValueError("CrewwellPDFParser supports only .pdf files")

        pdf = pdfium.PdfDocument(str(path))
        _ = len(pdf)
        pdf.close()

        page_texts: list[str] = []
        with pdfplumber.open(str(path)) as pdf_doc:
            for page in pdf_doc.pages:
                page_texts.append(page.extract_text() or "")

        return self.ensure_result_contract(self._parse_crewwell_profile(page_texts))

    def _parse_crewwell_profile(self, page_texts: list[str]) -> dict[str, Any]:
        result = self.empty_result()
        lines = self._normalize_lines(page_texts)
        if not lines:
            return result

        personal = result["personal_data"]
        applications = result["applications"]

        for idx, line in enumerate(lines):
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
                    rank = rank.split("Desired Vessel Type:", 1)[0].strip()
                if not rank and idx > 0:
                    prev_line = lines[idx - 1].strip()
                    if prev_line and ":" not in prev_line:
                        rank = prev_line
                if rank:
                    personal["position_applied_for"] = rank
                    personal["rank_applied_for"] = rank
                    applications.append({"position_applied_for": rank, "rank_applied_for": rank})
            if "Birthday / Place of birth:" in line:
                rest = line.split("Birthday / Place of birth:", 1)[1].strip()
                if not re.search(r"\d{2}\.\d{2}\.\d{4}", rest):
                    window = " ".join(lines[max(0, idx - 2) : min(len(lines), idx + 4)])
                    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+([A-Za-z][A-Za-z,\- ]+)", window)
                    if date_match:
                        rest = f"{date_match.group(1)} {date_match.group(2)}"
                m = re.match(r"(\d{2}\.\d{2}\.\d{4})\s+(.+)$", rest)
                if m:
                    personal["date_of_birth"] = m.group(1).strip()
                    place = m.group(2).strip().strip(",")
                    place = re.sub(r"\bMinimum salary\b.*$", "", place, flags=re.IGNORECASE).strip(" ,")
                    if idx + 1 < len(lines):
                        next_line = lines[idx + 1].strip()
                        if next_line and ":" not in next_line and len(next_line.split()) <= 4 and not re.search(r"\d{2}\.\d{2}\.\d{4}", next_line):
                            place = f"{place}, {next_line}"
                    elif idx + 2 < len(lines):
                        next_line = lines[idx + 2].strip()
                        if next_line and ":" not in next_line and len(next_line.split()) <= 4:
                            place = f"{place}, {next_line}"
                    personal["place_of_birth"] = place
            if line.startswith("Phones:"):
                phone_part = line.split("Phones:", 1)[1].strip()
                phone_part = phone_part.split("Citizenship:", 1)[0].strip()
                phone_match = re.search(r"\+\d[\d ]{7,}", phone_part)
                if phone_match:
                    personal["primary_phone"] = phone_match.group(0).strip()
            if line.startswith("E-mail:"):
                personal["email"] = line.split("E-mail:", 1)[1].strip().split(" ")[0]
                residence_match = re.search(r"\b([A-Z][A-Z ]+)/([A-Z][A-Z ]+)\b", line)
                if residence_match:
                    personal["country"] = residence_match.group(1).title().strip()
                    personal["city"] = residence_match.group(2).title().strip()
            if line.startswith("English level:"):
                personal["english_level"] = line.split("English level:", 1)[1].strip().split("Closest airport:")[0].strip()
            if line.startswith("USA visa valid up:"):
                visa_part = line.split("USA visa valid up:", 1)[1].strip()
                visa_date = visa_part.split("Schengen visa valid up:", 1)[0].strip()
                if visa_date:
                    personal["usa_visa_expiry_date"] = visa_date
                if "Schengen visa valid up:" in line:
                    schengen = line.split("Schengen visa valid up:", 1)[1].strip()
                    if schengen:
                        personal["visa_status_note"] = f"Schengen visa valid up: {schengen}"
            if "Citizenship:" in line:
                citizenship = line.split("Citizenship:", 1)[1].strip().split(" ")[0]
                personal["citizenship"] = citizenship
                personal["nationality"] = citizenship
            if line.startswith("Sex:"):
                gender_match = re.search(r"Sex:\s*([A-Za-z]+)", line)
                if gender_match:
                    personal["gender"] = gender_match.group(1).strip().lower()
                height_match = re.search(r"Height:\s*(\d+(?:\.\d+)?)", line)
                if height_match:
                    personal["height_cm"] = height_match.group(1).strip()
                weight_match = re.search(r"Weight:\s*(\d+(?:\.\d+)?)", line)
                if weight_match:
                    personal["weight_kg"] = weight_match.group(1).strip()
            if line.startswith("Additional e-mail:"):
                extra_email = line.split("Additional e-mail:", 1)[1].strip().split(" ")[0]
                if extra_email:
                    personal["secondary_email"] = extra_email
                phone_match = re.search(r"Additional phone:\s*(\+\d[\d ]+)", line)
                if phone_match:
                    personal["secondary_phone"] = phone_match.group(1).strip()
            if line.startswith("Next of kin:"):
                kin_rel = line.split("Next of kin:", 1)[1].strip().split("Kin phone:", 1)[0].strip()
                if kin_rel:
                    personal["next_of_kin_relationship"] = kin_rel
                kin_phone_match = re.search(r"Kin phone:\s*(\+\d[\d ]+)", line)
                if kin_phone_match:
                    personal["next_of_kin_phone"] = kin_phone_match.group(1).strip()
            if line.startswith("Kin name, Surname:"):
                kin_name = line.split("Kin name, Surname:", 1)[1].strip().split("Kin address:", 1)[0].strip()
                if kin_name:
                    personal["next_of_kin_full_name"] = kin_name
                if "Kin address:" in line:
                    kin_address = line.split("Kin address:", 1)[1].strip()
                    if kin_address:
                        personal["next_of_kin_address"] = kin_address
            if line.startswith("Maritime education:"):
                school = line.split("Maritime education:", 1)[1].strip()
                if not school and idx + 1 < len(lines):
                    candidate_school = lines[idx + 1].strip()
                    if candidate_school and ":" not in candidate_school:
                        school = candidate_school
                if school and school.lower() != "additional skills:":
                    personal["school_name"] = school
                elif idx + 1 < len(lines):
                    fallback_note = lines[idx + 1].strip()
                    if fallback_note:
                        personal["education_notes"] = fallback_note
                if idx + 1 < len(lines):
                    next_line = lines[idx + 1]
                    grad_match = re.search(r"\b(19|20)\d{2}\b", next_line)
                    if grad_match:
                        personal["graduation_year"] = grad_match.group(0)
                    if "Additional skills:" in next_line:
                        notes = next_line.split("Additional skills:", 1)[0].strip()
                        if notes:
                            personal["education_notes"] = notes

        self._parse_crewwell_documents(lines, result)
        self._parse_crewwell_certificates(lines, result)
        self._parse_crewwell_medical_certificates(lines, result)
        self._parse_crewwell_sea_service(lines, result)
        self._sync_medical_summary_from_certificates(result)
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

    def _parse_crewwell_documents(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Passports / Smbk")
        end = self._find_line_index(lines, "Diplomas")
        if start is None or end is None or end <= start:
            return
        known_titles = ("Seaman's book", "International passport", "National passport", "Passport")
        for line in lines[start + 1 : end]:
            if line.startswith("Title of document") or line.startswith("Rank"):
                continue
            parsed = self._parse_crewwell_document_line(line, known_titles)
            if parsed:
                result["documents"].append(parsed)

    def _parse_crewwell_certificates(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Certificates")
        if start is None:
            return
        end = self._find_first_index_from(lines, start + 1, {"Medical certificates", "Sea service (last 5 years)", "Biometrics"})
        if end is None:
            end = len(lines)
        pending_title: list[str] = []
        for line in lines[start + 1 : end]:
            if line.startswith("Title of document"):
                continue
            parsed = self._parse_crewwell_certificate_line(line, pending_title)
            if parsed:
                result["certificates"].append(parsed)
                pending_title = []
            elif not re.search(r"\d{2}\.\d{2}\.\d{4}", line):
                pending_title.append(line)

    def _parse_crewwell_sea_service(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Sea service (last 5 years)")
        if start is None:
            return
        end = self._find_first_index_from(lines, start + 1, {"Biometrics", "Additional info", "Next of Kin"})
        if end is None:
            end = len(lines)
        date_re = re.compile(r"\d{2}\.\d{2}\.\d{4}")
        sea_lines = lines[start + 1 : end]
        seen_periods: set[tuple[str, str]] = set()
        for idx, line in enumerate(sea_lines):
            dates_here = date_re.findall(line)
            if not dates_here:
                continue
            sign_on = dates_here[0]
            sign_off = dates_here[1] if len(dates_here) > 1 else None
            if sign_off is None:
                for look_ahead in range(idx + 1, min(len(sea_lines), idx + 4)):
                    next_dates = date_re.findall(sea_lines[look_ahead])
                    if next_dates:
                        candidate = next_dates[0]
                        if self._date_to_int(candidate) >= self._date_to_int(sign_on):
                            sign_off = candidate
                        break
            if sign_off is None:
                continue
            if self._date_to_int(sign_off) < self._date_to_int(sign_on):
                continue
            period = (sign_on, sign_off)
            if period in seen_periods:
                continue
            seen_periods.add(period)

            window = sea_lines[max(0, idx - 4) : min(len(sea_lines), idx + 5)]
            window_text = " ".join(window)
            prefix = line.split(sign_on, 1)[0].strip()

            item: dict[str, Any] = {
                "sign_on_date": sign_on,
                "sign_off_date": sign_off,
            }

            rank = self._extract_crewwell_rank(window_text)
            if rank:
                item["rank_on_vessel"] = rank

            vessel = self._extract_crewwell_vessel_name(prefix, window)
            if vessel:
                item["vessel_name"] = vessel

            vessel_type = self._extract_crewwell_vessel_type(window_text)
            if vessel_type:
                item["vessel_type"] = vessel_type

            dwt = self._extract_crewwell_dwt(window_text)
            if dwt:
                item["dwt"] = dwt

            result["sea_service"].append(item)

    def _parse_crewwell_medical_certificates(self, lines: list[str], result: dict[str, Any]) -> None:
        start = self._find_line_index(lines, "Medical certificates")
        if start is None:
            return
        end = self._find_first_index_from(lines, start + 1, {"Flag Documents and Other Countries Seaman's Books"})
        if end is None:
            end = len(lines)

        pending_title: list[str] = []
        for line in lines[start + 1 : end]:
            if line.startswith("Title of document"):
                continue
            dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", line)
            if not dates:
                pending_title.append(line.strip())
                continue

            text = line.strip()
            tokens = text.split()
            first_date_idx = next((i for i, token in enumerate(tokens) if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", token)), None)
            if first_date_idx is None:
                continue

            prefix = " ".join(tokens[:first_date_idx]).strip()
            title = " ".join(pending_title + [prefix]).strip() if pending_title else prefix
            pending_title = []
            if not title:
                continue
            number = None
            title_tokens = title.split()
            if title_tokens and re.fullmatch(r"\d+", title_tokens[-1]):
                number = title_tokens[-1]
                title = " ".join(title_tokens[:-1]).strip()
            if not title:
                continue

            issue_date = dates[0]
            expiry_date = dates[1] if len(dates) > 1 else None
            after_issue = text.split(issue_date, 1)[1].strip()
            country = None
            if after_issue:
                tail_tokens = after_issue.split()
                if tail_tokens:
                    if re.fullmatch(r"\d+", tail_tokens[0]):
                        number = tail_tokens[0]
                        tail_tokens = tail_tokens[1:]
                    if tail_tokens:
                        country = tail_tokens[0]
            cert_item: dict[str, Any] = {
                "certificate_type": title,
                "date_issued": issue_date,
            }
            if expiry_date:
                cert_item["expiry_date"] = expiry_date
            if number:
                cert_item["certificate_number"] = number
            if country:
                cert_item["country_of_issue"] = country
            result["certificates"].append(cert_item)

    @staticmethod
    def _sync_medical_summary_from_certificates(result: dict[str, Any]) -> None:
        personal = result.get("personal_data", {})
        for cert in result.get("certificates", []):
            cert_type = str(cert.get("certificate_type") or "").lower()
            if "medical certificate" in cert_type:
                if cert.get("certificate_number"):
                    personal["medical_fitness_certificate_number"] = cert.get("certificate_number")
                if cert.get("date_issued"):
                    personal["medical_fitness_issue_date"] = cert.get("date_issued")
                if cert.get("expiry_date"):
                    personal["medical_fitness_expiry_date"] = cert.get("expiry_date")
            if "yellow fever" in cert_type:
                if cert.get("date_issued"):
                    personal["yellow_fever_issue_date"] = cert.get("date_issued")
                if cert.get("expiry_date"):
                    personal["yellow_fever_expiry_date"] = cert.get("expiry_date")

    @staticmethod
    def _parse_crewwell_document_line(line: str, known_titles: tuple[str, ...]) -> dict[str, Any] | None:
        normalized = line.strip()
        if not normalized:
            return None
        date_matches = re.findall(r"\d{2}\.\d{2}\.\d{4}", normalized)
        if not date_matches:
            return None

        matched_title = next((title for title in known_titles if normalized.lower().startswith(title.lower())), None)
        if not matched_title:
            return None

        remainder = normalized[len(matched_title) :].strip()
        tokens = remainder.split()
        if not tokens:
            return {"document_type": matched_title}

        try:
            date_idx = next(i for i, token in enumerate(tokens) if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", token))
        except StopIteration:
            return {"document_type": matched_title}

        number = " ".join(tokens[:date_idx]).strip()
        issue_date = tokens[date_idx]
        tail = tokens[date_idx + 1 :]
        expiry_date = None
        if tail and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", tail[-1]):
            expiry_date = tail[-1]
            tail = tail[:-1]
        country = " ".join(tail).strip() or None

        item: dict[str, Any] = {"document_type": matched_title}
        if number:
            item["document_number"] = number
        if issue_date:
            item["date_of_issue"] = issue_date
        if expiry_date:
            item["date_of_expiry"] = expiry_date
        if country:
            item["country_of_issue"] = country
        return item

    @staticmethod
    def _parse_crewwell_certificate_line(line: str, pending_title: list[str]) -> dict[str, Any] | None:
        text = line.strip()
        if not text:
            return None
        date_matches = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
        if not date_matches:
            return None

        tokens = text.split()
        try:
            first_date_idx = next(i for i, token in enumerate(tokens) if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", token))
        except StopIteration:
            return None

        pre_tokens = tokens[:first_date_idx]
        if not pre_tokens:
            return None
        number_idx = max((i for i, token in enumerate(pre_tokens) if any(ch.isdigit() for ch in token)), default=-1)
        if number_idx == -1:
            return None

        number = pre_tokens[number_idx]
        title_tokens = pre_tokens[:number_idx]
        if pending_title:
            title_tokens = pending_title + title_tokens
        title = " ".join(title_tokens).strip()
        if not title:
            return None

        issue_date = tokens[first_date_idx]
        rest = tokens[first_date_idx + 1 :]
        expiry_date = None
        if rest and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", rest[-1]):
            expiry_date = rest[-1]
            rest = rest[:-1]
        country = " ".join(rest).strip() or None

        item: dict[str, Any] = {
            "certificate_type": title,
            "certificate_number": number,
            "date_issued": issue_date,
        }
        if expiry_date:
            item["expiry_date"] = expiry_date
        if country:
            item["country_of_issue"] = country
        return item

    @staticmethod
    def _extract_crewwell_rank(text: str) -> str | None:
        rank_patterns = [
            r"\bMaster\b",
            r"\bChief Officer\b",
            r"\bChief Engineer\b",
            r"\b2nd Officer\b",
            r"\b3rd Officer\b",
            r"\b2nd Engineer\b",
            r"\b3rd Engineer\b",
            r"\bBoatswain\b",
            r"\bAB Seaman\b",
        ]
        for pattern in rank_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _extract_crewwell_vessel_name(prefix: str, window: list[str]) -> str | None:
        if "/" in prefix:
            candidate = prefix.split("/", 1)[0].strip(" -")
            low = candidate.lower()
            if candidate and "carrier" not in low and "vessel type" not in low and "position vessel name" not in low:
                return candidate

        for line in window:
            if "/" in line:
                candidate = line.split("/", 1)[0].strip(" -")
                low = candidate.lower()
                if not candidate:
                    continue
                if any(
                    word in low
                    for word in (
                        "bulk carrier",
                        "oil",
                        "chemical",
                        "master",
                        "chief officer",
                        "chief engineer",
                        "vessel type",
                        "position vessel name",
                    )
                ):
                    continue
                return candidate
        return None

    @staticmethod
    def _extract_crewwell_vessel_type(text: str) -> str | None:
        for candidate in (
            "Oil/chemical tanker",
            "Crude Oil Tanker",
            "Oil Products Tanker",
            "Chemical tanker",
            "Bulk carrier",
            "General Cargo",
            "LNG",
        ):
            if candidate.lower() in text.lower():
                return candidate
        return None

    @staticmethod
    def _extract_crewwell_dwt(text: str) -> str | None:
        numbers = re.findall(r"\b(\d{4,6})\b", text)
        for num in numbers:
            value = int(num)
            if 1900 <= value <= 2100:
                continue
            if 3000 <= value <= 400000:
                return num
        return None

    @staticmethod
    def _date_to_int(value: str) -> int:
        try:
            d, m, y = value.split(".")
            return int(y) * 10000 + int(m) * 100 + int(d)
        except Exception:
            return 0

    @staticmethod
    def _find_line_index(lines: list[str], target: str) -> int | None:
        target_norm = " ".join(target.lower().split())
        for idx, line in enumerate(lines):
            line_norm = " ".join(line.lower().split())
            if line_norm == target_norm:
                return idx
        return None

    @staticmethod
    def _find_first_index_from(lines: list[str], start: int, targets: set[str]) -> int | None:
        normalized_targets = {" ".join(target.lower().split()) for target in targets}
        for idx in range(start, len(lines)):
            line_norm = " ".join(lines[idx].lower().split())
            if line_norm in normalized_targets:
                return idx
        return None
