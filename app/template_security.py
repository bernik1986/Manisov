"""Data-only template language and shared OOXML preflight.

Call validate_ooxml_archive before any DOCX/openpyxl load, inside a bounded
worker. This is not an operating-system sandbox or an Office macro scanner.
"""

from __future__ import annotations

from datetime import date, datetime
import math
from pathlib import Path, PurePosixPath
from types import BuiltinMethodType
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
import zlib

from jinja2 import StrictUndefined, Template, Undefined
from jinja2.runtime import LoopContext
from jinja2.sandbox import ImmutableSandboxedEnvironment, SecurityError, safe_range


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2048
MAX_CONTEXT_BYTES = 2 * 1024 * 1024
MAX_CONTEXT_NODES = 50000
MAX_CONTEXT_DEPTH = 24
MAX_RENDERED_TEXT = 16 * 1024 * 1024


class TemplateValidationError(ValueError):
    """Invalid, unsupported, or over-budget template input."""


def validate_ooxml_archive(path: Path) -> None:
    """Validate ZIP metadata AND streamed contents before OOXML library loads.

    Public shared contract for render/import workers. No extraction or writes.
    The caller must use a stable private copy to avoid replacement races.
    """
    try:
        if Path(path).stat().st_size > MAX_ARCHIVE_BYTES:
            raise TemplateValidationError("template_archive_size_limit")
        with ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise TemplateValidationError("template_archive_member_limit")
            names = set()
            total = 0
            for member in members:
                name = member.filename
                parts = PurePosixPath(name).parts
                if (not name or name.startswith("/") or "\\" in name or ":" in name
                        or "\x00" in name or ".." in parts or name in names):
                    raise TemplateValidationError("template_archive_invalid_member")
                names.add(name)
                if member.flag_bits & 1 or member.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                    raise TemplateValidationError("template_archive_unsupported_member")
                total += member.file_size
                if member.file_size > MAX_MEMBER_BYTES or total > MAX_EXPANDED_BYTES:
                    raise TemplateValidationError("template_archive_expanded_limit")
            if "[Content_Types].xml" not in names or not {
                "word/document.xml", "xl/workbook.xml"
            }.intersection(names):
                raise TemplateValidationError("template_archive_not_ooxml")
            total = 0
            for member in members:
                size = 0
                tail = b""
                with archive.open(member) as stream:
                    while chunk := stream.read(65536):
                        size += len(chunk)
                        total += len(chunk)
                        if size > MAX_MEMBER_BYTES or total > MAX_EXPANDED_BYTES:
                            raise TemplateValidationError("template_archive_expanded_limit")
                        if member.filename.lower().endswith((".xml", ".rels")):
                            # NUL removal also covers UTF-16/32 declarations.
                            probe = tail + chunk.replace(b"\x00", b"").upper()
                            if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
                                raise TemplateValidationError("template_archive_xml_declaration")
                            tail = probe[-16:]
                if size != member.file_size:
                    raise TemplateValidationError("template_archive_invalid_size")
    except (BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error, EOFError) as exc:
        raise TemplateValidationError("template_archive_invalid") from exc


_PATH_KEYS = frozenset({"candidate_photo_path", "file_path", "stored_path", "relative_path"})


def plain_template_context(context: dict) -> dict:
    """Copy exact builtins only; never call arbitrary str/deepcopy/serialization hooks."""
    if type(context) is not dict:
        raise TemplateValidationError("template_context_not_plain")
    nodes = 0
    size = 0

    def copy(value, depth=0):
        nonlocal nodes, size
        nodes += 1
        if nodes > MAX_CONTEXT_NODES or depth > MAX_CONTEXT_DEPTH:
            raise TemplateValidationError("template_context_limit")
        kind = type(value)
        if kind is str:
            if len(value) > MAX_CONTEXT_BYTES:
                raise TemplateValidationError("template_context_limit")
            size += len(value.encode("utf-8"))
            if size > MAX_CONTEXT_BYTES:
                raise TemplateValidationError("template_context_limit")
            return value
        if value is None or kind is bool:
            return value
        if kind is int and value.bit_length() <= 64:
            return value
        if kind is float and math.isfinite(value):
            return value
        if kind in {date, datetime}:
            return value.strftime("%d-%m-%Y")
        if kind in {list, tuple}:
            if len(value) > MAX_CONTEXT_NODES:
                raise TemplateValidationError("template_context_limit")
            return [copy(item, depth + 1) for item in value]
        if kind is dict:
            if len(value) > MAX_CONTEXT_NODES:
                raise TemplateValidationError("template_context_limit")
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise TemplateValidationError("template_context_not_plain")
                if key.startswith("_") or key in _PATH_KEYS:
                    continue
                result[copy(key, depth + 1)] = copy(item, depth + 1)
            return result
        raise TemplateValidationError("template_context_not_plain")

    return copy(context)


class _BoundedTemplate(Template):
    def render(self, *args, **kwargs):
        chunks = []
        size = 0
        for chunk in self.generate(*args, **kwargs):
            size += len(chunk.encode("utf-8"))
            if size > MAX_RENDERED_TEXT:
                raise TemplateValidationError("template_text_limit")
            chunks.append(chunk)
        return "".join(chunks)


_DICT_METHODS = frozenset({"items", "keys", "values", "get"})
_LOOP_ATTRIBUTES = frozenset({
    "index", "index0", "revindex", "revindex0", "first", "last", "length",
    "depth", "depth0", "previtem", "nextitem",
})
_FILTERS = frozenset({
    "abs", "batch", "capitalize", "center", "count", "d", "default", "dictsort",
    "e", "escape", "first", "float", "forceescape", "format", "groupby", "indent",
    "int", "items", "join", "last", "length", "list", "lower", "map", "max", "min",
    "pprint", "reject", "rejectattr", "replace", "reverse", "round", "safe",
    "select", "selectattr", "slice", "sort", "string", "striptags", "sum", "title",
    "trim", "truncate", "unique", "upper", "urlencode", "wordcount", "wordwrap",
})


class TemplateEnvironment(ImmutableSandboxedEnvironment):
    """Only dict data, sequence indices, and inert loop metadata are accessible.

    Deny before Python getattr, including on InlineImage. No generic attr filter,
    string methods, object-producing globals, loader, or arbitrary callables.
    """

    template_class = _BoundedTemplate
    intercepted_binops = frozenset({"*", "**"})

    def __init__(self, *, autoescape=False, strict_undefined=True):
        super().__init__(undefined=StrictUndefined if strict_undefined else Undefined, autoescape=autoescape,
                         finalize=lambda value: "" if value is None else value)
        self.globals.clear()
        self.globals["range"] = safe_range
        self.filters = {key: value for key, value in self.filters.items() if key in _FILTERS}

    def is_safe_attribute(self, obj, attr, value):
        return ((type(obj) is dict and attr in _DICT_METHODS)
                or (type(obj) is LoopContext and attr in _LOOP_ATTRIBUTES))

    def is_safe_callable(self, obj):
        return obj is safe_range or (type(obj) is BuiltinMethodType and type(obj.__self__) is dict
                and obj.__name__ in _DICT_METHODS)

    def getattr(self, obj, attribute):
        if attribute.startswith("_"):
            raise SecurityError("template_attribute_denied")
        if type(obj) is dict:
            if attribute in _DICT_METHODS:
                return getattr(obj, attribute)
            if attribute in obj:
                return obj[attribute]
            return self.undefined(name=attribute)
        if type(obj) is LoopContext and attribute in _LOOP_ATTRIBUTES:
            return getattr(obj, attribute)
        raise SecurityError("template_attribute_denied")

    def getitem(self, obj, argument):
        if isinstance(argument, str) and argument.startswith("_"):
            raise SecurityError("template_attribute_denied")
        if type(obj) in {dict, list, tuple, str}:
            try:
                return obj[argument]
            except (TypeError, LookupError):
                if type(obj) is dict and isinstance(argument, str):
                    return self.getattr(obj, argument)
                return self.undefined(name=argument)
        raise SecurityError("template_attribute_denied")

    def call_binop(self, context, operator, left, right):
        if operator == "**" and (type(right) not in {int, float} or abs(right) > 32):
            raise TemplateValidationError("template_expression_limit")
        if operator == "*":
            for value, count in ((left, right), (right, left)):
                if type(value) in {str, list, tuple} and type(count) is int:
                    if len(value) * count > MAX_RENDERED_TEXT:
                        raise TemplateValidationError("template_expression_limit")
        return super().call_binop(context, operator, left, right)
