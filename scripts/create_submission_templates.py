"""Create built-in ПОДАЧА info-list DOCX templates under templates/Podacha/."""

from pathlib import Path

from docx import Document


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "templates" / "Podacha"

NEW_CANDIDATE_LINES = [
    (
        "Please kindly let us introduce {{ rank }} {{ surname }} {{ first_name }} for the opening "
        "m/v {{ opening_vessel }}, foll kind request of the Company."
    ),
    "Kindly be informed, {{ passport_visa_status_note }}",
    "",
    "{{ rank_since_sentence }}",
    "",
    "{% if leaving_reason %}The reason the gent left his companies is {{ leaving_reason }}.{% endif %}",
    "{% if employer_reference_note %}{{ employer_reference_note }}{% endif %}",
    "",
    "{% if ecdis_systems_text %}Experience with ECDIS: {{ ecdis_systems_text }}{% endif %}",
    "",
    "English: {{ english_level }}",
    "Home airport: {{ home_airport }}",
    "Date Available: {{ date_available_display }}",
    "{% if vaccination_summary %}Vaccination: {{ vaccination_summary }}{% endif %}",
    "",
    "{% if desirable_salary_display %}Desirable salary: {{ desirable_salary_display }}{% endif %}",
    "{% if contract_duration_display %}Desirable duration of contract: {{ contract_duration_display }}{% endif %}",
    "",
    "{{ sb_expiry_paragraph }}",
    "",
    "Please advise if the gent can be considered.",
]

EX_CREW_LINES = [
    (
        "Please kindly let us introduce ex-crew from m/v {{ previous_vessel }} {{ rank }} "
        "{{ surname }} {{ first_name }} for the opening on m/v {{ opening_vessel }}."
    ),
    "",
    "Please note, {{ passport_visa_status_note }}",
    "",
    "{{ rank_since_sentence }}",
    "",
    "{% if ecdis_systems_text %}Experience with ECDIS: {{ ecdis_systems_text }}{% endif %}",
    "",
    "English: {{ english_level }}",
    "",
    "Home Airport: {{ home_airport }}",
    "",
    "Date Available: {{ date_available_display }}",
    "",
    "{% if vaccination_summary %}Vaccination : {{ vaccination_summary }}{% endif %}",
    "",
    "{% if desirable_salary_display %}Desirable salary: {{ desirable_salary_display }}{% endif %}",
    "{% if contract_duration_display %}Desirable duration of contract: {{ contract_duration_display }}{% endif %}",
    "",
    "{{ coc_gmdss_expiry_note }}",
    "",
    "{{ coc_qr_paragraph }}",
    "",
    "{{ usa_visa_valid_paragraph }}",
    "",
    "Please advise if the gent can be considered.",
]


def write_template(file_name: str, lines: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(OUT_DIR / file_name)


def main() -> None:
    write_template("инфо лист для подачи новых кандидатов.docx", NEW_CANDIDATE_LINES)
    write_template("инфо лист для подачи эксов.docx", EX_CREW_LINES)


if __name__ == "__main__":
    main()
