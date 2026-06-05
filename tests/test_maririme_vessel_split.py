from __future__ import annotations

from parser.pdf_parser import PDFParser, _split_maririme_vessel_detail_line


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
