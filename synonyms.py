from __future__ import annotations

import re


def normalize_label(label: str) -> str:
    """Normalize raw form label for stable dictionary lookup."""
    value = label.strip().lower()
    # Word often stores typographic apostrophe (U+2019) instead of ASCII 0x27 — unify for synonym keys.
    for ch in ("\u2019", "\u2018", "\u201b", "\u2032", "\u00b4", "\u02bc"):
        value = value.replace(ch, "'")
    value = value.replace("&", " and ")
    # Remove common option tails often printed in merged field captions.
    value = re.sub(r"\bmarried\s*/\s*single\b", "", value)
    value = re.sub(r"\byes\s*/\s*no\b", "", value)
    value = re.sub(r"\bmale\s*/\s*female\b", "", value)
    value = re.sub(r"\bnationality\s*/\s*age\b", "nationality age", value)
    value = re.sub(r"\bcitizenship\s*/\s*age\b", "citizenship age", value)
    value = re.sub(r"[`'\".:;,+/\\()\-]+", " ", value)
    value = re.sub(r"\bno\s+of\b", "number of", value)
    value = re.sub(r"\byrs?\b", "years", value)
    value = re.sub(r"\btele(phone)?\s*no\b", "telephone number", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


_CANONICAL_TO_SYNONYMS: dict[str, list[str]] = {
    "position_applied_for": [
        "Position to Apply for",
        "Applied for the position of",
        "Rank applied for",
        "Position applied for",
    ],
    "surname": ["Surname", "Last Name", "Family Name", "Last name as in passport", "Family/Surname"],
    "first_name": ["First Name", "Forename", "Given Name", "Name", "Given/First Name"],
    "middle_name": ["Middle Name", "Patronymic"],
    "full_name": ["Full Name", "Seaman Name", "Applicant Name"],
    "date_of_birth": ["Date of Birth", "Birth Date", "DOB", "Date / Place of Birth", "Date of birth (dd/mm/yyyy)"],
    "place_of_birth": ["Place of Birth", "Date/Place of birth", "Place born"],
    "nationality": ["Nationality", "Nationality / Age", "Nationality/Age", "Nationality (as in passport)"],
    "citizenship": ["Citizenship", "Citizen", "Citizenship / Age"],
    "age": ["Age", "Citizenship / Age", "Nationality / Age", "Years of age"],
    "permanent_address": ["Address", "Home address", "Permanent Address", "Permanent address"],
    "primary_phone": [
        "Phones /Mob/EMAIL",
        "Telephone No.",
        "Tel.",
        "Phones",
        "Mobile No.",
        "Mobile",
        "Mob",
        "Phone",
        "Phone No.",
        "Telephone number",
        "Contact Number",
    ],
    "email": ["EMAIL", "E-MAIL", "e-mail", "email", "Email Address", "E-mail address"],
    "skype_id": ["Skype id", "Skype ID"],
    "father_name": [
        "Father's Name",
        "Father's name",
        "Father name",
        "Name of Father",
        "Fathers Name",
        "Father",
        "Имя отца",
        "ФИО отца",
    ],
    "mother_name": [
        "Mother's Name",
        "Mother's name",
        "Mother name",
        "Name of Mother",
        "Mothers Name",
        "Mother",
        "Имя матери",
        "ФИО матери",
    ],
    "marital_status": ["Marital Status", "Marital status", "Marital status Married/Single", "Marital status (M/S)"],
    "spouse_name": ["Spouse's name", "Spouse name"],
    "number_of_children": [
        "Children",
        "Number of Children",
        "Children:",
        "Dependants",
        "Sons",
        "Daughters",
    ],
    "beneficiary_full_name": ["Name of Beneficiary", "Beneficiary"],
    "beneficiary_relationship": ["Relation", "Relationship", "Relation to beneficiary"],
    "beneficiary_phone": ["Beneficiary phone"],
    "next_of_kin_relationship": ["Next of kin", "Relation to next of kin", "Next of kin relationship"],
    "next_of_kin_full_name": [
        "Next of kin name",
        "Surname + Forename in next of kin block",
        "Name of next of kin",
    ],
    "highest_educational_attainment": ["Highest Educational Attainment", "Education", "Highest education"],
    "school_name": ["School", "College", "Academy"],
    "graduation_year": ["Year", "Graduation Year"],
    "english_level": ["English Ability", "English", "English level", "English proficiency", "Spoken English"],
    "english_certificate": ["Certificate", "English Certificate"],
    "other_languages": ["Other Language", "Other languages"],
    "height_cm": ["Height (cm)", "Height"],
    "height_m": ["Height (m)"],
    "weight_kg": ["Weight (kg)", "Weight (kgs)", "Weight"],
    "distinctive_marks": ["Distinctive Marks", "Marks"],
    "passport_number": ["Passport No.", "Passport", "Passport Number", "Passport No", "No. of Passport"],
    "passport_issue_date": ["Date of Issue", "Date Issued", "Issue Date"],
    "passport_expiry_date": ["Date of Validity", "Expiry Date", "Date of Expiry", "Valid Until", "Expiry"],
    "passport_place_of_issue": ["Place of Issue", "Issuing Authority", "Issued at", "Place/Authority of issue"],
    "seaman_book_number": [
        "Seaman's Book No.",
        "Seaman's book",
        "Seaman Book",
        "Seaman book number",
        "Seaman Book No",
        "Seaman's Book Number",
    ],
    "usa_visa_number": ["USA Visa No.", "US Visa", "Visa Number", "USA Visa Number", "US Visa No"],
    "yellow_fever_vaccination": ["Yellow Fever Vaccination", "Yellow Fever", "Yellow fever vaccine"],
    "certificate_of_competency_rank": [
        "Cert. of Competency Rank",
        "Certificate of Competency Rank",
        "COC Rank",
        "National License (C.O.C)",
    ],
    "certificate_of_competency_number": ["Certificate No", "COC Number", "License Number", "Cert No", "Certificate #"],
    "total_sea_service": [
        "Total Sea Service",
        "Sea Service",
        "Total sea service",
        "Total Sailing Service",
        "Total sailing time",
        "Total Sea Time",
    ],
    "total_sea_service_in_rank": [
        "Total Sea Service in Rank",
        "Years in Rank",
        "Sea Service in Rank",
        "Total Sea Time in Rank",
        "Sea service in present rank",
        "Years of service in Rank",
        "Years Of Service In Rank",
    ],
    "years_as_watch_officer": [
        "Years as Watch Officer",
        "Watchkeeping experience",
        "Watch officer experience",
        "Years of service in Watch Keeping Duties",
        "Years of service in watch keeping duties",
    ],
    "proposed_vessel": ["PROPOSE VESSEL", "Vessel", "Vessel type"],
    "date_applied": ["Date Applied", "Application Date", "Date of Application"],
    "date_available": ["Date available", "Available from", "Availability", "Date Available"],
    "last_salary_usd": ["Last Salary (USD)", "Previous Salary", "Last salary"],
    "erp_no": ["ERP No."],
    "e_registration_no": ["E-registration No"],
    "application_form_no": ["Application/Personal Data Form - No", "Application/Personal Data Form – No"],
    "cv_prepared_by": ["CV prepared by", "Prepared by", "CV prepared/checked by"],
    "application_id": ["Application ID"],
    "record_status": ["Record Status", "Status"],
    "source_form_type": ["Source Form Type", "Form Type"],
    "source_file_name": ["Source File Name", "Original File Name"],
    "cv_imported": ["CV Imported", "Imported from CV"],
    "ukr_contract_json": ["Ukrainian contract JSON", "UKR contract fields"],
    "latin_full_name": ["Latin Full Name", "Name in Latin"],
    "native_full_name": ["Native Full Name", "Name in Native Language"],
    "country_of_birth": ["Country of Birth"],
    "gender": ["Gender", "Sex", "Male / Female"],
    "secondary_phone": ["Secondary Phone", "Alternative Phone"],
    "mobile_phone": ["Mobile Phone", "Mobile No", "Cell Phone"],
    "telephone_no": ["Telephone No", "Telephone Number", "Landline"],
    "secondary_email": ["Secondary Email", "Alternative Email"],
    "home_address": ["Home Address"],
    "current_address": ["Current Address"],
    "city": ["City", "Town"],
    "region": ["Region", "State/Province"],
    "postal_code": ["Postal Code", "Zip Code"],
    "country": ["Country", "Country of Residence"],
    "children_under_18_count": ["Children Under 18", "No. of Children Below 18 yrs. Old"],
    "dependants_count": ["Dependants Count", "Dependants"],
    "sons_count": ["Sons Count", "Sons"],
    "daughters_count": ["Daughters Count", "Daughters"],
    "beneficiary_address": ["Beneficiary Address", "Address of Beneficiary"],
    "next_of_kin_surname": ["Next of kin Surname", "Surname of next of kin"],
    "next_of_kin_first_name": ["Next of kin First Name", "Forename of next of kin"],
    "next_of_kin_address": ["Next of kin Address", "Address of next of kin"],
    "next_of_kin_phone": ["Next of kin Phone", "Phone of next of kin"],
    "education_notes": ["Education Notes", "Education remarks"],
    "native_language": ["Native Language", "Mother Tongue"],
    "current_rank": ["Current Rank", "Present Rank", "Rank"],
    "watchkeeping_capacity": ["Watchkeeping Capacity"],
    "years_in_rank": ["Years in Rank"],
    "years_in_this_type_of_vessel": [
        "Years in this type of vessel",
        "Years of service in this type of Vessel",
        "Years of service in this type of vessel",
    ],
    "years_in_all_types_of_tankers": ["Years in all types of tankers"],
    "total_years_of_sea_service": ["Total years of Sea Service", "Total Years of Sea Service"],
    "rank_experience_summary": ["Rank experience summary"],
    "bulk_carrier_years_in_rank": ["Bulk carrier years in rank"],
    "bulk_carrier_years_in_vessel_type": ["Bulk carrier years in vessel type"],
    "tanker_years_in_rank": ["Tanker years in rank"],
    "tanker_years_in_this_tanker_type": ["Tanker years in this tanker type"],
    "tanker_years_in_all_tanker_types": ["Tanker years in all tanker types"],
    "watch_officer_since_year": ["Watch officer since year"],
    "oil_tanker_experience": ["Oil tanker experience"],
    "chemical_tanker_experience": ["Chemical tanker experience"],
    "gas_tanker_experience": ["Gas tanker experience"],
    "lng_experience": ["LNG experience"],
    "lpg_experience": ["LPG experience"],
    "container_experience": ["Container experience"],
    "bulk_carrier_experience": ["Bulk carrier experience"],
    "general_cargo_experience": ["General cargo experience"],
    "offshore_experience": ["Offshore experience"],
    "medical_fitness_certificate_number": ["Medical Fitness Certificate Number", "Medical certificate number"],
    "medical_fitness_issue_date": ["Medical Fitness Issue Date", "Medical certificate issue date"],
    "medical_fitness_expiry_date": ["Medical Fitness Expiry Date", "Medical certificate expiry date"],
    "yellow_fever_issue_date": ["Yellow Fever Issue Date"],
    "yellow_fever_expiry_date": ["Yellow Fever Expiry Date"],
    "yellow_fever_unlimited": ["Yellow Fever Unlimited"],
    "usa_visa_issue_date": ["USA Visa Issue Date", "US Visa Issue Date"],
    "usa_visa_expiry_date": ["USA Visa Expiry Date", "US Visa Expiry Date"],
    "usa_visa_place_of_issue": ["USA Visa Place Of Issue", "US Visa Place Of Issue"],
    "visa_status_note": ["Visa Status Note", "Visa remarks"],
    "home_airport": ["Home Airport", "Home airport", "Nearest airport", "Closest airport"],
    "departure_airport": ["Departure Airport", "Departure airport", "Airport of departure"],
    "desirable_salary_usd": ["Desirable Salary USD", "Desirable salary", "Expected salary USD"],
    "rejoin_bonus_usd": ["Rejoin Bonus USD", "Rejoin bonus", "Re-join bonus"],
    "submission_contract_duration_text": [
        "Contract Duration",
        "Contract duration",
        "Desired contract duration",
    ],
    "ecdis_systems_text": ["ECDIS Systems", "ECDIS systems", "ECDIS experience"],
    "vaccination_summary": ["Vaccination Summary", "Vaccinations", "Vaccination status"],
    "leaving_reason": ["Leaving Reason", "Reason for leaving", "Reason left company"],
    "employer_reference_note": ["Employer Reference", "Employer reference note", "Reference from employer"],
    "passport_visa_status_note": ["Passport Visa Status", "Passport/visa status", "Visa and passport status"],
    "coc_gmdss_expiry_note": ["COC GMDSS Expiry", "COC/GMDSS expiry note", "Certificate expiry note"],
    "coc_has_qr_codes": ["COC Has QR Codes", "COC QR codes", "Certificates have QR codes"],
}


SYNONYM_MAP: dict[str, str] = {}
for canonical, raw_labels in _CANONICAL_TO_SYNONYMS.items():
    SYNONYM_MAP[normalize_label(canonical)] = canonical
    for raw in raw_labels:
        SYNONYM_MAP[normalize_label(raw)] = canonical


def get_canonical_field(label: str) -> str | None:
    """Return canonical CRM field name for an input form label."""
    if not label:
        return None
    return SYNONYM_MAP.get(normalize_label(label))
