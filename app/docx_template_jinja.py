"""Patch DOCX Jinja that falls back from empty numbers to slot codes."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

# docxtpl: empty number must stay empty even if template uses default(cert.certificate_code).
_JINJA_NUMBER_FALLBACK_RE = re.compile(
    r"(\{\{[^}]*?)(certificate_number|document_number)\|default\([^|}]*?(certificate_code|certificate_type|document_type)[^}]*?\)",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_MAILTO_EMAIL_RE = re.compile(r"mailto:\s*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})", re.IGNORECASE)

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_W_HYPERLINK = f"{{{_NS_W}}}hyperlink"
_W_T = f"{{{_NS_W}}}t"
_R_ID = f"{{{_NS_R}}}id"

ET.register_namespace("w", _NS_W)
ET.register_namespace("r", _NS_R)


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


def _plain_email_text(text: str) -> str:
    patched = _MAILTO_EMAIL_RE.sub(r"\1", text)
    return re.sub(r"mailto:\s*", "", patched, flags=re.IGNORECASE)


def _element_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.text:
            parts.append(node.text)
    return "".join(parts)


def _sanitize_text_nodes(root: ET.Element) -> int:
    count = 0
    for node in root.iter(_W_T):
        if node.text and "mailto:" in node.text.lower():
            patched = _plain_email_text(node.text)
            if patched != node.text:
                node.text = patched
                count += 1
    return count


def _unwrap_email_hyperlinks(root: ET.Element, rel_targets: dict[str, str]) -> int:
    count = 0
    for parent in list(root.iter()):
        children = list(parent)
        for child in children:
            if child.tag != _W_HYPERLINK:
                continue
            rid = child.attrib.get(_R_ID, "")
            target = rel_targets.get(rid, "")
            visible_text = _element_text(child)
            should_unwrap = (
                target.lower().startswith("mailto:")
                or "mailto:" in visible_text.lower()
                or bool(_EMAIL_RE.search(visible_text))
            )
            if not should_unwrap:
                continue
            insert_at = list(parent).index(child)
            tail = child.tail
            parent.remove(child)
            replacement_children = list(child)
            for offset, replacement in enumerate(replacement_children):
                parent.insert(insert_at + offset, replacement)
            if tail:
                if replacement_children:
                    replacement_children[-1].tail = (replacement_children[-1].tail or "") + tail
                elif insert_at > 0:
                    prev = list(parent)[insert_at - 1]
                    prev.tail = (prev.tail or "") + tail
            count += 1
    return count


def _rels_targets(rels_xml: bytes | None) -> dict[str, str]:
    if not rels_xml:
        return {}
    try:
        root = ET.fromstring(rels_xml)
    except ET.ParseError:
        return {}
    targets: dict[str, str] = {}
    for rel in root:
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            targets[rel_id] = target
    return targets


def _remove_mailto_rels(rels_xml: bytes | None) -> tuple[bytes | None, int]:
    if not rels_xml:
        return rels_xml, 0
    try:
        root = ET.fromstring(rels_xml)
    except ET.ParseError:
        return rels_xml, 0
    removed = 0
    for rel in list(root):
        target = rel.attrib.get("Target", "")
        if target.lower().startswith("mailto:"):
            root.remove(rel)
            removed += 1
    if removed == 0:
        return rels_xml, 0
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), removed


def _rels_name_for_xml_part(xml_name: str) -> str:
    rels_base = xml_name.rsplit("/", 1)[-1] + ".rels"
    return "word/_rels/" + rels_base


def _is_word_content_xml(name: str) -> bool:
    return (
        name == "word/document.xml"
        or name.startswith("word/header")
        or name.startswith("word/footer")
        or name.startswith("word/footnotes")
        or name.startswith("word/endnotes")
    ) and name.endswith(".xml")


def strip_email_hyperlinks_from_docx(path: Path) -> int:
    """Make rendered email placeholders plain text, removing mailto hyperlinks."""
    with ZipFile(path, "r") as zin:
        names = zin.namelist()
        chunks = {name: zin.read(name) for name in names}

    replacements = 0
    for name in names:
        if not _is_word_content_xml(name):
            continue
        try:
            root = ET.fromstring(chunks[name])
        except ET.ParseError:
            continue
        rels_name = _rels_name_for_xml_part(name)
        rel_targets = _rels_targets(chunks.get(rels_name))
        replacements += _sanitize_text_nodes(root)
        replacements += _unwrap_email_hyperlinks(root, rel_targets)
        if replacements:
            chunks[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        if rels_name in chunks:
            patched_rels, removed = _remove_mailto_rels(chunks[rels_name])
            if patched_rels is not None and removed:
                chunks[rels_name] = patched_rels
                replacements += removed

    if replacements == 0:
        return 0

    tmp = path.with_suffix(path.suffix + ".email_tmp")
    with ZipFile(tmp, "w", compression=ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, chunks[name])
    shutil.move(str(tmp), str(path))
    return replacements
