from datetime import date
from zipfile import ZipFile

from docx import Document
from openpyxl import Workbook, load_workbook
from PIL import Image
import pytest

from app.template_renderer import render_docx_template, render_excel_template, render_template_to_file
from app.template_security import TemplateValidationError


def make_template(path, text):
    if path.suffix == ".docx":
        doc = Document()
        doc.add_paragraph(text)
        doc.save(path)
    else:
        book = Workbook()
        book.active["A1"] = text
        book.save(path)
    return path


def read_text(path):
    if path.suffix == ".docx":
        return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    book = load_workbook(path)
    try:
        return book.active["A1"].value
    finally:
        book.close()


@pytest.mark.parametrize("suffix", [".docx", ".xlsx", ".xlsm"])
def test_isolated_formats_preserve_ordinary_language(tmp_path, suffix):
    source = make_template(tmp_path / ("source" + suffix),
                           "{{ name|upper }} {{ current_date }} {% for key, value in fields.items() %}"
                           "{{ loop.index }}:{{ key }}={{ value }};{% endfor %}{{ missing|default('ok') }}")
    original = source.read_bytes()
    output = tmp_path / ("result" + suffix)
    render_template_to_file(source, {"name": "Ada", "current_date": date(2026, 11, 20), "fields": {"rank": "CO"}}, output)
    assert read_text(output) == "ADA 20-11-2026 1:rank=CO;ok"
    assert source.read_bytes() == original


@pytest.mark.parametrize("populated", [False, True])
def test_docx_optional_placeholders_conditionals_and_loops(tmp_path, populated):
    source = make_template(tmp_path / "source.docx",
                           "{{ name }}|{{ salary_company }}|{{ ukr_contract_number }}|"
                           "{% if salary_company %}company{% else %}no company{% endif %}|"
                           "{{ salary_rank or 'unassigned' }}|{{ optional_note|default('none') }}|"
                           "{{ record.note }}|{{ contacts[0] }}|"
                           "{% for item in optional_rows %}{{ item }}{% else %}no rows{% endfor %}")
    original = source.read_bytes()
    context = {"name": "Ada", "record": {}, "contacts": []}
    if populated:
        context.update(salary_company="Demo & Co", ukr_contract_number="C-1", salary_rank="CO",
                       optional_note="ready", record={"note": "ok"}, contacts=["Demo"], optional_rows=["one"])
    output = tmp_path / "output.docx"
    render_docx_template(source, context, output)
    assert read_text(output) == (
        "Ada|Demo & Co|C-1|company|CO|ready|ok|Demo|one" if populated else
        "Ada|||no company|unassigned|none|||no rows"
    )
    assert source.read_bytes() == original


def test_docx_secondary_parts_allow_missing_optional_fields(tmp_path):
    source = tmp_path / "source.docx"
    doc = Document()
    doc.add_paragraph("{{ name }}")
    doc.sections[0].header.paragraphs[0].text = "Company: {{ salary_company }}"
    doc.sections[0].footer.paragraphs[0].text = "{% if ukr_contract_number %}Contract{% else %}Draft{% endif %}"
    doc.core_properties.title = "Candidate {{ optional_title }}"
    doc.save(source)
    output = tmp_path / "output.docx"
    render_docx_template(source, {"name": "Ada"}, output)
    rendered = Document(output)
    assert rendered.paragraphs[0].text == "Ada"
    assert rendered.sections[0].header.paragraphs[0].text == "Company: "
    assert rendered.sections[0].footer.paragraphs[0].text == "Draft"
    assert rendered.core_properties.title == "Candidate "


@pytest.mark.parametrize("suffix", [".xlsx", ".xlsm"])
@pytest.mark.parametrize("text", ["{{ salary_company }}", "{% if salary_company %}Company{% endif %}"])
def test_excel_missing_fields_remain_strict(tmp_path, suffix, text):
    source = make_template(tmp_path / ("source" + suffix), text)
    output = tmp_path / ("output" + suffix)
    with pytest.raises(TemplateValidationError):
        render_excel_template(source, {}, output)
    assert not output.exists()


@pytest.mark.parametrize("suffix", [".docx", ".xlsx", ".xlsm"])
@pytest.mark.parametrize("text", ["{{ record._hidden }}", "{{ record.clear() }}"])
def test_formats_reject_benign_disallowed_access_without_publishing(tmp_path, suffix, text):
    source = make_template(tmp_path / ("source" + suffix), text)
    output = tmp_path / ("result" + suffix)
    output.write_bytes(b"existing output")
    with pytest.raises(TemplateValidationError):
        render_template_to_file(source, {"record": {"name": "Ada"}}, output)
    assert output.read_bytes() == b"existing output"
    assert not list(tmp_path.glob(".template-*"))


@pytest.mark.parametrize("part", ["header", "footer", "property"])
def test_docx_secondary_parts_use_same_sandbox(tmp_path, part):
    source = tmp_path / "source.docx"
    doc = Document()
    doc.add_paragraph("{{ name }}")
    if part == "property":
        doc.core_properties.title = "{{ record.clear() }}"
    else:
        getattr(doc.sections[0], part).paragraphs[0].text = "{{ record.clear() }}"
    doc.save(source)
    with pytest.raises(TemplateValidationError):
        render_docx_template(source, {"name": "Ada", "record": {}}, tmp_path / "output.docx")


def test_docx_patching_and_escaping_do_not_mutate_source_or_context(tmp_path):
    source = make_template(tmp_path / "source.docx", "{{ certificate.certificate_number|default(certificate.certificate_code, true) }} {{ name }}")
    original = source.read_bytes()
    context = {"certificate": {"certificate_number": "", "certificate_code": "COC"}, "name": "Ada & Co <test>"}
    output = tmp_path / "output.docx"
    render_docx_template(source, context, output)
    assert source.read_bytes() == original
    assert context["certificate"]["certificate_number"] == ""
    assert read_text(output) == " Ada & Co <test>"


@pytest.mark.parametrize("suffix", [".docx", ".xlsx", ".xlsm"])
def test_photo_alias_still_embeds_image_without_exposing_attributes(tmp_path, suffix):
    photo = tmp_path / "portrait.png"
    Image.new("RGB", (20, 30), "green").save(photo)
    source = make_template(tmp_path / ("source" + suffix), "{{ photo }}")
    output = tmp_path / ("output" + suffix)
    render_template_to_file(source, {"candidate_photo_path": str(photo)}, output)
    with ZipFile(output) as archive:
        assert any("/media/" in name for name in archive.namelist())
    source = make_template(source, "{{ photo.tpl }}")
    with pytest.raises(TemplateValidationError):
        render_template_to_file(source, {"candidate_photo_path": str(photo)}, output)


def test_excel_formula_guard_and_original_formulas(tmp_path):
    source = tmp_path / "source.xlsx"
    book = Workbook()
    book.active["A1"] = "{{ text }}"
    book.active["B1"] = "=1+{{ number }}"
    book.save(source)
    output = tmp_path / "output.xlsx"
    render_excel_template(source, {"text": "=1+1", "number": 2}, output)
    result = load_workbook(output)
    assert result.active["A1"].value == "'=1+1"
    assert result.active["B1"].value == "=1+2"
    result.close()


@pytest.mark.parametrize("suffix", [".docx", ".xlsx", ".xlsm"])
def test_invalid_ooxml_rejected_in_worker(tmp_path, suffix):
    source = tmp_path / ("source" + suffix)
    source.write_bytes(b"not a ZIP")
    output = tmp_path / ("result" + suffix)
    with pytest.raises(TemplateValidationError):
        render_template_to_file(source, {}, output)
    assert not output.exists()
