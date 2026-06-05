"""
Maritime rank / position normalization for search filters.
Deterministic: synonym map, preprocessing, regex expansions, then highest-precedence match.
"""
from __future__ import annotations

import re
# Canonical -> aliases (as provided). First key is the standard label returned by normalize.
CANONICAL_ALIASES: dict[str, list[str]] = {
    "Master": [
        "Captain",
        "Capt",
        "Cpt",
        "Master Mariner",
        "Ship Master",
        "Vessel Master",
        "Master/Captain",
        "Master Captain",
        "MSTR",
        "MST",
        "CAPT MASTER",
    ],
    "Chief Officer": [
        "Chief Mate",
        "C/O",
        "CO",
        "Ch Off",
        "Chief Deck Officer",
        "First Officer",
        "1st Officer",
        "1/O",
        "I/O",
        "1O",
        "1-O",
        "First Mate",
        "Chief Mate Officer",
        "OOW II/2 Chief",
        "II/2 Chief Mate",
    ],
    "Second Officer": [
        "Second Mate",
        "2nd Officer",
        "2nd Mate",
        "2/O",
        "2O",
        "II/O",
        "II-O",
        "II O",
        "Second Deck Officer",
        "Navigation Officer",
        "Navigational Officer",
        "OOW",
        "Officer of the Watch",
        "OOW II/1",
        "II/1 OOW",
        "II-1 OOW",
    ],
    "Third Officer": [
        "Third Mate",
        "3rd Officer",
        "3rd Mate",
        "3/O",
        "3O",
        "III/O",
        "III-O",
        "III O",
        "OOW III/1",
        "III/1 OOW",
        "III-1 OOW",
    ],
    "Deck Cadet": [
        "Deck Cadet Officer",
        "Deck Trainee",
        "Deck Apprentice",
        "Trainee Deck Officer",
        "Apprentice Deck Officer",
        "Cadet Deck",
        "Deck Intern",
        "Deck Student",
        "Officer Cadet",
        "O/C",
        "OC",
        "D/C",
        "DC",
    ],
    "Boatswain": [
        "Bosun",
        "Bo'sun",
        "Boatswain Bosun",
        "Deck Foreman",
        "Lead AB",
        "Senior AB",
        "Head Deck Rating",
    ],
    "Able Seaman": [
        "AB",
        "A/B",
        "Able Bodied Seaman",
        "Able-Bodied Seaman",
        "Able Seafarer Deck",
        "ASD",
        "Able Deck Rating",
        "Able Seaman II/4",
        "II/4 Rating",
    ],
    "Ordinary Seaman": [
        "OS",
        "O/S",
        "Ordinary Seafarer",
        "Deck Rating",
        "Junior Seaman",
        "Deck Boy",
        "Trainee Seaman",
        "Deck Helper",
    ],
    "Chief Engineer": [
        "Chief Engineer Officer",
        "C/E",
        "CE",
        "Chief Eng",
        "Chief Marine Engineer",
        "Head Engineer",
        "Ch Eng",
        "C ENG",
        "Chief Engineer Class I",
    ],
    "Second Engineer": [
        "Second Engineer Officer",
        "2nd Engineer",
        "2/E",
        "2E",
        "Second Assistant Engineer",
        "First Assistant Engineer",
        "Senior Engineer",
        "II Engineer",
        "II/E",
        "2 Eng",
        "Second Eng",
    ],
    "Third Engineer": [
        "Third Engineer Officer",
        "3rd Engineer",
        "3/E",
        "3E",
        "Third Assistant Engineer",
        "Second Assistant Engineer",
        "III Engineer",
        "III/E",
        "3 Eng",
    ],
    "Fourth Engineer": [
        "Fourth Engineer Officer",
        "4th Engineer",
        "4/E",
        "4E",
        "Fourth Assistant Engineer",
        "Junior Engineer",
        "IV Engineer",
        "IV/E",
        "4 Eng",
    ],
    "Engine Cadet": [
        "Engine Cadet Officer",
        "Engine Trainee",
        "Cadet Engineer",
        "Trainee Engineer",
        "Engine Apprentice",
        "Engine Intern",
        "E/C",
        "EC",
        "Engine Student",
    ],
    "Chief Officer Trainee": [
        "chief officer trainee",
        "chief mate trainee",
        "chief officer cadet",
        "chief mate cadet",
        "trainee chief officer",
        "trainee chief mate",
        "старший помощник стажер",
        "старпом стажер",
        "стажер старшего помощника",
        "кадет старшего помощника",
    ],
    "Second Engineer Trainee": [
        "second engineer trainee",
        "2nd engineer trainee",
        "second engineer cadet",
        "2/e trainee",
        "2/e cadet",
        "trainee second engineer",
        "стажер второго механика",
        "второй механик стажер",
        "кадет второго механика",
        "2-й механик стажер",
    ],
    "Junior Officer": [
        "junior officer",
        "jr officer",
        "jr. officer",
        "junior deck officer",
        "junior engineer officer",
        "junior marine officer",
        "assistant officer",
        "trainee officer",
        "deck officer trainee",
        "engine officer trainee",
        "младший офицер",
        "младший помощник",
        "младший судовой офицер",
        "офицер-стажер",
        "помощник офицера",
    ],
    "Electro Technical Officer": [
        "ETO",
        "E.T.O",
        "Electrotechnical Officer",
        "Electro Technical Officer",
        "Electrical Officer",
        "Electro Tech Officer",
        "E Officer",
        "Electro Officer",
    ],
    "Electrician": [
        "electrician",
        "ship electrician",
        "marine electrician",
        "electrical engineer",
        "судовой электрик",
        "электрик",
        "электромеханик",
        "электроофицер",
        "судовой электромеханик",
    ],
    "Gas Engineer": [
        "gas engineer",
        "gas engineer officer",
        "lng gas engineer",
        "lpg gas engineer",
        "gas officer",
        "cargo gas engineer",
        "gas plant engineer",
        "gas technician",
        "gas specialist",
        "инженер по газу",
        "газовый инженер",
        "газовый механик",
        "газовый офицер",
        "инженер газовой установки",
        "специалист по газовым системам",
    ],
    "Motorman": [
        "Motor Man",
        "Engine Rating",
        "Engine Room Rating",
        "Qualified Motorman",
        "QMED",
        "Engine Watch Rating",
        "Oilman",
        "Greaser",
        "Machinery Rating",
    ],
    "Wiper": [
        "Engine Wiper",
        "Engine Room Wiper",
        "Junior Engine Rating",
        "Engine Trainee Rating",
        "Engine Cleaner",
        "Machinery Cleaner",
    ],
    "Fitter": [
        "Engine Fitter",
        "Marine Fitter",
        "Fitter Welder",
        "Welder",
        "Engine Room Fitter",
        "Repairman",
        "Pipe Fitter",
        "Mechanical Fitter",
        "Ship Fitter",
        "Steel Worker",
    ],
    "Pumpman": [
        "pumpman",
        "pump man",
        "pump-man",
        "pump operator",
        "cargo pumpman",
        "tanker pumpman",
        "пампман",
        "помпман",
        "насосчик",
        "оператор насосов",
        "оператор грузовых насосов",
    ],
    "Oiler": [
        "oiler",
        "oilman",
        "lubricator",
        "engine room attendant",
        "engine crew",
        "масленщик",
        "машинная команда",
        "рядовой машинного отделения",
    ],
    "Cook": [
        "cook",
        "ship cook",
        "chief cook",
        "cook steward",
        "galley cook",
        "судовой повар",
        "повар",
        "кок",
        "шеф-повар",
        "судовой кок",
    ],
}

# Higher rank = lower index. Used when multiple canons match the same string.
RANK_PRECEDENCE: tuple[str, ...] = (
    "Master",
    "Chief Engineer",
    "Chief Officer",
    "Chief Officer Trainee",
    "Second Engineer",
    "Second Engineer Trainee",
    "Second Officer",
    "Third Engineer",
    "Third Officer",
    "Fourth Engineer",
    "Electro Technical Officer",
    "Gas Engineer",
    "Junior Officer",
    "Deck Cadet",
    "Engine Cadet",
    "Electrician",
    "Boatswain",
    "Pumpman",
    "Able Seaman",
    "Ordinary Seaman",
    "Cook",
    "Motorman",
    "Oiler",
    "Wiper",
    "Fitter",
)

RANK_INDEX: dict[str, int] = {name: i for i, name in enumerate(RANK_PRECEDENCE)}

# Dropdown order for Seamens Data (same as RANK_PRECEDENCE).
RANK_OPTIONS: tuple[str, ...] = RANK_PRECEDENCE

# (pattern, replacement) — applied in order. Patterns run on preprocessed (no dots/slashes) string.
# Replacements are lowercase phrases; final matching uses preprocess on full text again.
_RE_CANON: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\biv\s*e\b", re.I), "fourth engineer"),
    (re.compile(r"\biii\s*o\b", re.I), "third officer"),
    (re.compile(r"\bii\s*o\b", re.I), "second officer"),
    (re.compile(r"\biio\b", re.I), "second officer"),
    (re.compile(r"\biiio\b", re.I), "third officer"),
    (re.compile(r"\b1\s*o\b", re.I), "chief officer"),
    (re.compile(r"\b1o\b", re.I), "chief officer"),
    (re.compile(r"\b2\s*e\b", re.I), "second engineer"),
    (re.compile(r"\b2e\b", re.I), "second engineer"),
    (re.compile(r"\b2\s*o\b", re.I), "second officer"),
    (re.compile(r"\b2o\b", re.I), "second officer"),
    (re.compile(r"\b3\s*e\b", re.I), "third engineer"),
    (re.compile(r"\b3e\b", re.I), "third engineer"),
    (re.compile(r"\b3\s*o\b", re.I), "third officer"),
    (re.compile(r"\b3o\b", re.I), "third officer"),
    (re.compile(r"\b4\s*e\b", re.I), "fourth engineer"),
    (re.compile(r"\b4e\b", re.I), "fourth engineer"),
    (re.compile(r"\beto\b", re.I), "electro technical officer"),
]

# Slash abbreviations before fuzzy scan (avoids C/O matching both Chief Officer and Deck Cadet via "co"/"oc").
_SLASH_RANK_EXACT: dict[str, str] = {
    "c/o": "Chief Officer",
    "1/o": "Chief Officer",
    "2/o": "Second Officer",
    "3/o": "Third Officer",
    "o/c": "Deck Cadet",
    "d/c": "Deck Cadet",
    "c/e": "Chief Engineer",
    "2/e": "Second Engineer",
    "3/e": "Third Engineer",
    "4/e": "Fourth Engineer",
}


def _slash_rank_canonical(raw: str) -> str | None:
    compact = re.sub(r"\s+", "", (raw or "").strip().lower().replace("-", "/"))
    if not compact:
        return None
    return _SLASH_RANK_EXACT.get(compact)


def preprocess(raw_rank: str) -> str:
    s = (raw_rank or "").lower().strip()
    for ch in ".-/\u00a0":
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _regex_apply_to_spaced_version(s: str) -> str:
    """User rules also treat slashes as removed without spaces; we match digit+officer via _RE_CANON on compact form too."""
    out = s
    for pat, rep in _RE_CANON:
        out = pat.sub(f" {rep} ", out)
    return re.sub(r"\s+", " ", out).strip()


def _no_space_copy(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _regex_on_compact(s_compact: str) -> str:
    out = s_compact
    for pat, rep in _RE_CANON:
        out = pat.sub(rep.replace(" ", ""), out)  # tight replacement for 2o style
    return out


def _expand_string_for_scan(raw: str) -> str:
    p = preprocess(raw)
    s1 = _regex_apply_to_spaced_version(p)
    compact = _no_space_copy(p)
    compact2 = _regex_on_compact(compact)
    spaced_from_compact = re.sub(r"([a-z])([0-9])|([0-9])([a-z])", r"\1\3 \2\4", compact2)
    spaced_from_compact = re.sub(r"([0-9])([a-z])", r"\1 \2", spaced_from_compact)
    merged = f"{p} {s1} {_no_space_copy(compact2)} {spaced_from_compact} {preprocess(s1)}"
    return re.sub(r"\s+", " ", merged).strip().lower()


def _token_present(alias_lower: str, scan_lower: str) -> bool:
    if len(alias_lower) < 2:
        return False
    return bool(
        re.search(rf"(?<![a-z0-9]){re.escape(alias_lower)}(?![a-z0-9])", scan_lower)
    ) or (len(alias_lower) >= 4 and alias_lower in scan_lower)


def _all_canons_matching_in_scan(scan: str) -> set[str]:
    found: set[str] = set()
    for canon, aliases in CANONICAL_ALIASES.items():
        for a in (canon, *aliases):
            ap = preprocess(a)
            if not ap or len(ap) < 2:
                continue
            if _token_present(ap, scan):
                found.add(canon)
                break
    return found


def display_position_label(raw: str | None) -> str | None:
    """Canonical rank for UI lists/filters, or trimmed original if no mapping."""
    text = (raw or "").strip()
    if not text:
        return None
    canon = resolve_canonical_position(text)
    return canon if canon else text


def _longest_matching_alias_len(canon: str, scan_l: str) -> int:
    best = 0
    for a in (canon, *CANONICAL_ALIASES[canon]):
        ap = preprocess(a)
        if not ap or len(ap) < 2:
            continue
        if _token_present(ap, scan_l):
            best = max(best, len(ap))
    return best


def resolve_canonical_position(raw: str) -> str | None:
    """
    Map text to a canonical rank using synonyms. When several ranks match, prefer the
    longest matching alias (e.g. "Engine Cadet" over bare "Cadet"), not table precedence.
    """
    if not (raw or "").strip():
        return None
    slash_canon = _slash_rank_canonical(raw)
    if slash_canon:
        return slash_canon
    scan = _expand_string_for_scan(raw)
    scan_l = scan.lower()
    if not scan_l:
        return None
    matched = _all_canons_matching_in_scan(scan_l)
    if not matched:
        return None
    if len(matched) > 1:
        trainee_markers = ("trainee", "cadet", "стажер", "кадет", "стажёр")
        if any(marker in scan_l for marker in trainee_markers):
            trainee_canons = [c for c in matched if "trainee" in c.lower() or "cadet" in c.lower()]
            if trainee_canons:
                return max(trainee_canons, key=lambda c: _longest_matching_alias_len(c, scan_l))
        non_cadet = [c for c in matched if "cadet" not in c.lower()]
        if non_cadet:
            return max(non_cadet, key=lambda c: _longest_matching_alias_len(c, scan_l))
    return max(matched, key=lambda c: _longest_matching_alias_len(c, scan_l))


def canonical_rank_for_storage(raw: str | None) -> str | None:
    """
    Canonical label to persist on application/sea-service fields.
    Returns None when raw text should be kept as-is (free-text titles, E2E markers, etc.).
    """
    text = (raw or "").strip()
    if not text:
        return None
    slash = _slash_rank_canonical(text)
    if slash:
        return slash
    canon = resolve_canonical_position(text)
    if not canon:
        return None
    if text.lower() == canon.lower():
        return canon
    if preprocess(text) == preprocess(canon):
        return canon
    if len(text) <= 12:
        return canon
    return None


# Too-short tokens are unsafe for SQL ILIKE '%term%' (e.g. "co" in "Second", "ce" in "officer").
_SQL_ILIKE_SUBSTRING_BLOCKLIST: frozenset[str] = frozenset(
    {
        "co",
        "ce",
        "io",
        "eng",
        "1o",
        "2o",
        "3o",
        "4o",
        "i o",
        "1 o",
        "2 o",
        "3 o",
        "4 o",
        "c e",
    }
)


def _unique_terms_for_sql(strings: list[str], max_len: int = 500) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in strings:
        st = t.strip()[:max_len] if t else ""
        st = st.replace("%", "").replace("_", "")
        if not st:
            continue
        k = st.lower()
        if k in seen:
            continue
        if k in _SQL_ILIKE_SUBSTRING_BLOCKLIST:
            continue
        seen.add(k)
        out.append(st)
    return out


def expand_canonical(canon: str) -> list[str]:
    al = [canon, *CANONICAL_ALIASES[canon]]
    extra: list[str] = []
    for t in al:
        p = preprocess(t)
        compact = _no_space_copy(preprocess(t))
        for x in (t, p):
            if x and re.sub(r"\s+", " ", str(x).strip()):
                extra.append(re.sub(r"\s+", " ", str(x).strip()))
        if compact and len(compact) >= 4 and re.sub(r"\s+", " ", compact.strip()):
            extra.append(re.sub(r"\s+", " ", compact.strip()))
    return _filter_sql_terms_for_canonical(canon, _unique_terms_for_sql(extra))


def _term_pollutes_other_rank(canon: str, term: str) -> bool:
    """True when a SQL ILIKE term would also match a different canonical rank label."""
    tl = term.lower().strip()
    if not tl:
        return True
    for other in RANK_PRECEDENCE:
        if other == canon:
            continue
        if tl not in other.lower():
            continue
        if other.startswith(f"{canon} "):
            continue
        return True
    return False


def _filter_sql_terms_for_canonical(canon: str, terms: list[str]) -> list[str]:
    return [t for t in terms if not _term_pollutes_other_rank(canon, t)]


def position_search_terms(user_input: str) -> list[str]:
    """
    Build OR-list of phrases for SQL ILIKE: either expanded synonyms for a resolved canonical
    or a single cleaned fragment if no mapping.
    """
    raw = (user_input or "").strip()
    if not raw:
        return []
    canon = resolve_canonical_position(raw)
    if canon:
        return expand_canonical(canon)
    return _unique_terms_for_sql([raw])


__all__ = [
    "CANONICAL_ALIASES",
    "RANK_PRECEDENCE",
    "RANK_OPTIONS",
    "preprocess",
    "display_position_label",
    "resolve_canonical_position",
    "position_search_terms",
    "expand_canonical",
    "_filter_sql_terms_for_canonical",
]
