from datetime import date
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from jinja2 import TemplateError
from jinja2.sandbox import SecurityError

from app import template_security as security
from app.docx_template_jinja import patch_docx_file, strip_email_hyperlinks_from_docx


def archive_fixture(path, extra=None):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return path


def test_plain_context_drops_paths_and_private_data_and_copies():
    original = {"current_date": date(2026, 11, 20), "_internal": "ignored",
                "candidate_photo_path": "portrait.jpg", "rows": [{"name": "Ada", "file_path": "local"}]}
    result = security.plain_template_context(original)
    assert result == {"current_date": "20-11-2026", "rows": [{"name": "Ada"}]}
    result["rows"][0]["name"] = "Changed"
    assert original["rows"][0]["name"] == "Ada"


def test_plain_context_never_invokes_object_hooks():
    class Record:
        def __str__(self):
            pytest.fail("must not stringify a runtime object")

        def __deepcopy__(self, memo):
            pytest.fail("must not copy a runtime object")

    with pytest.raises(security.TemplateValidationError, match="not_plain"):
        security.plain_template_context({"row": Record()})
    with pytest.raises(security.TemplateValidationError, match="not_plain"):
        security.plain_template_context({"callback": lambda: "unused"})


def test_plain_context_limits(monkeypatch):
    monkeypatch.setattr(security, "MAX_CONTEXT_BYTES", 4)
    with pytest.raises(security.TemplateValidationError, match="limit"):
        security.plain_template_context({"x": "12345"})
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(security.TemplateValidationError, match="limit"):
        security.plain_template_context({"x": cyclic})


def test_ordinary_loop_dictionary_methods_filters_and_none():
    env = security.TemplateEnvironment()
    template = env.from_string(
        "{% for key, value in record.items() %}{{ loop.index }}:{{ key|upper }}={{ value|default('', true) }};{% endfor %}"
        "{{ rows|map(attribute='name')|join(',') }}|{{ record.get('missing', 'ok') }}|{{ empty }}"
    )
    assert template.render(record={"a": "yes", "b": None}, rows=[{"name": "Ada"}], empty=None) == "1:A=yes;2:B=;Ada|ok|"
    assert set(env.globals) == {"range"} and env.loader is None
    assert env.from_string("{% for n in range(3) %}{{ n }}{% endfor %}").render() == "012"


@pytest.mark.parametrize("source", [
    "{{ row._hidden }}", "{{ row['_hidden'] }}", "{{ row.clear() }}",
    "{{ text.upper() }}", "{{ row|attr('items') }}", "{{ callback() }}",
])
@pytest.mark.parametrize("strict_undefined", [True, False])
def test_private_attributes_and_unapproved_calls_rejected(source, strict_undefined):
    with pytest.raises(TemplateError):
        security.TemplateEnvironment(strict_undefined=strict_undefined).from_string(source).render(
            row={}, text="hello", callback=lambda: "hello",
        )


@pytest.mark.parametrize("strict_undefined", [True, False])
def test_attribute_policy_denies_before_evaluating_property(strict_undefined):
    class Record:
        @property
        def name(self):
            pytest.fail("unapproved property must not be evaluated")

    with pytest.raises(SecurityError):
        security.TemplateEnvironment(strict_undefined=strict_undefined).getattr(Record(), "name")


def test_optional_fields_are_opt_in_without_changing_environment_policy():
    source = "{{ salary_company }}|{% if salary_company %}present{% else %}absent{% endif %}"
    with pytest.raises(TemplateError):
        security.TemplateEnvironment().from_string(source).render()
    optional = security.TemplateEnvironment(strict_undefined=False)
    assert optional.from_string(source).render() == "|absent"
    assert set(optional.globals) == {"range"} and optional.loader is None


def test_text_budget_uses_small_benign_loop(monkeypatch):
    monkeypatch.setattr(security, "MAX_RENDERED_TEXT", 8)
    with pytest.raises(security.TemplateValidationError, match="text_limit"):
        security.TemplateEnvironment().from_string("{% for row in rows %}{{ row }}{% endfor %}").render(rows=["1234"] * 3)


@pytest.mark.parametrize("limit,value", [
    ("MAX_ARCHIVE_BYTES", 10), ("MAX_ARCHIVE_MEMBERS", 1),
    ("MAX_MEMBER_BYTES", 4), ("MAX_EXPANDED_BYTES", 16),
])
def test_preflight_small_benign_archives_over_lowered_limits(tmp_path, monkeypatch, limit, value):
    path = archive_fixture(tmp_path / "fixture.docx")
    monkeypatch.setattr(security, limit, value)
    with pytest.raises(security.TemplateValidationError, match="limit"):
        security.validate_ooxml_archive(path)


def test_preflight_streams_integrity_and_rejects_invalid_metadata(tmp_path):
    valid = archive_fixture(tmp_path / "valid.docx")
    security.validate_ooxml_archive(valid)
    invalid = archive_fixture(tmp_path / "invalid.docx", {"../unused.txt": "benign"})
    with pytest.raises(security.TemplateValidationError, match="invalid_member"):
        security.validate_ooxml_archive(invalid)
    with pytest.warns(UserWarning):
        with ZipFile(valid, "a") as archive:
            archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(security.TemplateValidationError, match="invalid_member"):
        security.validate_ooxml_archive(valid)


@pytest.mark.parametrize("function", [security.validate_ooxml_archive, patch_docx_file, strip_email_hyperlinks_from_docx])
def test_archive_helpers_reject_invalid_zip_before_reading(tmp_path, function):
    path = tmp_path / "invalid.docx"
    path.write_bytes(b"not an Office document")
    with pytest.raises(security.TemplateValidationError):
        function(path)


def test_xml_declaration_policy_with_empty_benign_doctype(tmp_path):
    path = archive_fixture(tmp_path / "fixture.docx", {"word/header1.xml": "<!DOCTYPE header><header/>"})
    with pytest.raises(security.TemplateValidationError, match="xml_declaration"):
        security.validate_ooxml_archive(path)
