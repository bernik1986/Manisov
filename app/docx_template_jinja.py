"""Patch DOCX Jinja that falls back from empty numbers to slot codes."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

# docxtpl: empty number must stay empty even if template uses default(cert.certificate_code).
_JINJA_NUMBER_FALLBACK_RE = re.compile(
    r"(\{\{[^}]*?)(certificate_number|document_number)\|default\([^|}]*?(certificate_code|certificate_type|document_type)[^}]*?\)",
    re.IGNORECASE,
)


def patch_docx_number_jinja(xml: str) -> tuple[str, int]:
    """Remove Jinja default(...) to code/type when rendering number fields."""

    def _repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        field = match.group(2)
        return f"{prefix}{field}|default('', true)"

    patched, count = _JINJA_NUMBER_FALLBACK_RE.subn(_repl, xml)
    return patched, count


def patch_docx_file(path: Path) -> int:
    """Patch word/document.xml inside a DOCX. Returns number of replacements."""
    with ZipFile(path, "r") as zin:
        names = zin.namelist()
        chunks = {name: zin.read(name) for name in names}
    xml = chunks.get("word/document.xml")
    if not xml:
        return 0
    text = xml.decode("utf-8", errors="ignore")
    patched, count = patch_docx_number_jinja(text)
    if count == 0:
        return 0
    chunks["word/document.xml"] = patched.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".patch_tmp")
    with ZipFile(tmp, "w", compression=ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, chunks[name])
    shutil.move(str(tmp), str(path))
    return count
