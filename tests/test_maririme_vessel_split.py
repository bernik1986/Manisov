from __future__ import annotations

from parser.pdf_parser import PDFParser, _parse_maririme_build_detail_line, _split_maririme_vessel_detail_line


def test_split_nyedov_janina_row() -> None:
    raw = 'm/v "Janina" Antigua and Barbuda Clingenberg Bereederungs'
    out = _split_maririme_vessel_detail_line(raw)
    assert out["vessel_name"] == 'm/v "Janina"'
    assert out["flag"] == "Antigua and Barbuda"
    assert out["employer"] == "Clingenberg Bereederungs"
    assert "main_engine" not in out or not out.get("main_engine")


def test_split_nyedov_orion_row() -> None:
    raw = 'm/v "Orion" Antigua and Barbuda MAN B&W ME Jurgenhans'
    out = _split_maririme_vessel_detail_line(raw)
    assert out["vessel_name"] == 'm/v "Orion"'
    assert out["flag"] == "Antigua and Barbuda"
    assert out["main_engine"] == "MAN B&W ME"
    assert out["employer"] == "Jurgenhans"


def test_split_nyedov_future_row() -> None:
    raw = "m/v Future Marshall Islands Delligen-Holding"
    out = _split_maririme_vessel_detail_line(raw)
    assert out["vessel_name"] == "m/v Future"
    assert out["flag"] == "Marshall Islands"
    assert out["employer"] == "Delligen-Holding"


def test_split_nyedov_plain_name_row() -> None:
    raw = "Vitus Bering Bahamas Gestmar Tehnica"
    out = _split_maririme_vessel_detail_line(raw)
    assert out["vessel_name"] == "Vitus Bering"
    assert out["flag"] == "Bahamas"
    assert out["employer"] == "Gestmar Tehnica"


def test_parse_maririme_build_detail_line_with_year_and_agency() -> None:
    out = _parse_maririme_build_detail_line("2019 63000 7,220 Olive Crew")

    assert out["year_built"] == "2019"
    assert out["dwt"] == "63000"
    assert out["engine_power"] == "7,220"
    assert out["manning_agency"] == "Olive Crew"


def test_parse_maririme_build_detail_line_with_split_agency() -> None:
    out = _parse_maririme_build_detail_line("2021 64000 7,300 Agency", "Olive Crew management")

    assert out["year_built"] == "2021"
    assert out["dwt"] == "64000"
    assert out["engine_power"] == "7,300"
    assert out["manning_agency"] == "Olive Crew management"


def test_parse_maririme_profile_extracts_birth_physical_data_and_build_years() -> None:
    text = """
ivdwork69@gmail.com
Igor Dudchenko, 49
24-02-1976 +420722452303
+380506844387
Position Desired Wage Rate Employment Status
Chief Engineer $10,000 On vacation
Citizenship Residence Closest Airport
Ukraine Czech Republic Episkopi Airport
EXPERIENCE
Chief Engineer - Bulk Carrier 02.06.2025 - 05.11.2025 (5 months, 3 days)
Vessel Name Vessel flag ME Type Vessel owner
Aquavita Trust Marshall Islands Kawasaki Olive Ship Management
Build Year DWT ME Power, kW Agency
2019 63000 7,220 Olive Crew
Chief Engineer - Bulk Carrier 05.03.2024 - 24.08.2024 (5 months, 19 days)
Vessel Name Vessel flag ME Type Vessel owner
Aquavita Lime Marshall Islands MAN B&W ME Olive Ship Management
Build Year DWT ME Power, kW
2021 64000 7,300 Agency
Olive Crew management
PERSONAL INFORMATION
Height, cm Weight, kg Shoe size, cm Overall Size Hair Color Eye Color
186 97 44 56 Blond Gray
"""

    result = PDFParser.ensure_result_contract(PDFParser()._parse_maririme_profile([text]))
    personal = result["personal_data"]
    sea_service = result["sea_service"]

    assert personal["date_of_birth"] == "1976-02-24"
    assert personal["height_cm"] == "186"
    assert personal["weight_kg"] == "97"
    assert personal["citizenship"] == "Ukraine"
    assert personal["age"] == "49"
    assert sea_service[0]["year_built"] == "2019"
    assert sea_service[1]["year_built"] == "2021"
    assert sea_service[1]["manning_agency"] == "Olive Crew management"


def test_parse_nyedov_pdf_sea_service_flags(tmp_path) -> None:
    pdf = tmp_path / "nyedov.pdf"
    source = r"C:\Users\berni\Downloads\CV_Andriy_Nyedov.pdf"
    if not __import__("pathlib").Path(source).is_file():
        return
    import shutil

    shutil.copy(source, pdf)
    result = PDFParser().parse(pdf)
    sea = result["sea_service"]
    assert len(sea) == 5
    assert sea[0]["vessel_name"] == 'm/v "Janina"'
    assert sea[0]["flag"] == "Antigua and Barbuda"
    assert sea[0]["employer"] == "Clingenberg Bereederungs"
    assert sea[0]["manning_agency"] == "Marlow Navigation"
