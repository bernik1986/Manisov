"""
Fleet / vessel-type normalization for Seamens Data list and filters.
Canonical labels only in UI; SQL filter expands synonyms.
"""

from __future__ import annotations

import re

from app.rank_normalization import preprocess

# Canonical -> aliases (user-provided + common form variants).
CANONICAL_ALIASES: dict[str, list[str]] = {
    "Bulk Carrier": [
        "bulk carrier",
        "bulker",
        "bulk vessel",
        "bulkcarrier",
        "dry bulk carrier",
        "dry cargo bulk carrier",
        "dry bulker",
        "ore carrier",
        "coal carrier",
        "grain carrier",
        "cement carrier",
        "self unloading bulker",
        "self-unloader",
        "балкер",
        "сухогруз навалочный",
        "навалочник",
        "рудовоз",
        "углевоз",
        "зерновоз",
    ],
    "General Cargo Vessel": [
        "general cargo vessel",
        "general cargo ship",
        "general cargo",
        "cargo vessel",
        "cargo ship",
        "break bulk vessel",
        "breakbulk vessel",
        "conventional cargo vessel",
        "freighter",
        "dry cargo vessel",
        "dry cargo ship",
        "single decker",
        "tween decker",
        "сухогруз",
        "генеральный груз",
        "судно генерального груза",
        "грузовое судно",
        "универсальный сухогруз",
    ],
    "Container Vessel": [
        "container vessel",
        "container ship",
        "containership",
        "container",
        "boxship",
        "box ship",
        "container carrier",
        "cellular container ship",
        "feeder container ship",
        "feeder container",
        "feeder vessel",
        "контейнеровоз",
        "контейнерное судно",
        "фидер",
        "фидерный контейнеровоз",
    ],
    "LNG Carrier": [
        "lng carrier",
        "lng tanker",
        "lng",
        "liquefied natural gas carrier",
        "liquefied natural gas tanker",
        "gas carrier lng",
        "lng vessel",
        "membrane lng",
        "moss type lng",
        "газовоз lng",
        "лнг",
        "танкер спг",
        "судно для перевозки спг",
        "судно для перевозки сжиженного природного газа",
    ],
    "LPG Carrier": [
        "lpg carrier",
        "lpg tanker",
        "lpg",
        "liquefied petroleum gas carrier",
        "liquefied petroleum gas tanker",
        "gas carrier lpg",
        "lpg vessel",
        "fully refrigerated lpg",
        "semi refrigerated lpg",
        "pressurized lpg",
        "газовоз lpg",
        "лпг",
        "танкер lpg",
        "судно для перевозки lpg",
        "судно для перевозки сжиженного нефтяного газа",
    ],
    "Oil/Chemical Tanker": [
        "oil/chemical tanker",
        "oil chemical tanker",
        "oil and chemical tanker",
        "product/chemical tanker",
        "product chemical tanker",
        "parcel tanker",
        "imo chemical/product tanker",
        "imo chemical product tanker",
        "chemical/oil products tanker",
        "chemical oil products tanker",
    ],
    "Chemical Tanker": [
        "chemical tanker",
        "chemical carrier",
        "chem tanker",
        "parcel chemical tanker",
        "imo chemical tanker",
        "stainless steel chemical tanker",
        "химовоз",
        "химический танкер",
        "танкер-химовоз",
        "танкер для химических грузов",
    ],
    "Crude Oil Tanker": [
        "crude oil tanker",
        "crude tanker",
        "oil tanker",
        "crude carrier",
        "crude oil carrier",
        "tanker vessel",
        "suezmax",
        "aframax",
        "panamax tanker",
        "нефтяной танкер",
        "сырой нефтяной танкер",
        "танкер для сырой нефти",
    ],
    "VLCC": [
        "vlcc",
        "very large crude carrier",
        "very large crude oil carrier",
        "vlcc tanker",
        "large crude carrier",
        "large oil tanker",
        "ulcc",
    ],
    "Tug": [
        "tugboat",
        "towboat",
        "towing vessel",
        "harbour tug",
        "harbor tug",
        "escort tug",
        "anchor handling tug",
        "aht",
        "буксир",
    ],
    "Passenger Vessel": [
        "passenger vessel",
        "passenger ship",
        "cruise ship",
        "ferry",
        "ro-pax",
        "ropax",
        "roro passenger ship",
        "passenger ferry",
        "high speed craft",
        "hsc",
        "пассажирское судно",
        "круизное судно",
        "паром",
    ],
    "Offshore Vessel": [
        "offshore vessel",
        "offshore support vessel",
        "osv",
        "platform supply vessel",
        "psv",
        "anchor handling tug supply vessel",
        "ahts",
        "crew boat",
        "crew transfer vessel",
        "ctv",
        "multi-purpose support vessel",
        "mpsv",
        "diving support vessel",
        "dsv",
        "offshore construction vessel",
        "ocv",
        "оффшорное судно",
    ],
    "Heavy-Lift Vessel": [
        "heavy-lift vessel",
        "heavy lift vessel",
        "heavy-lift ship",
        "heavy lift ship",
        "heavy load carrier",
        "project cargo vessel",
        "project carrier",
        "semi-submersible heavy lift vessel",
        "hlv",
    ],
    "Reefer": [
        "reefer vessel",
        "refrigerated cargo ship",
        "refrigerated vessel",
        "refrigerated carrier",
        "fruit carrier",
        "frozen cargo vessel",
        "cold cargo vessel",
        "рефрижератор",
    ],
    "Ro-Ro": [
        "ro-ro",
        "roro",
        "roll-on/roll-off vessel",
        "roll on roll off ship",
        "car carrier",
        "vehicle carrier",
        "pure car carrier",
        "pcc",
        "pure car and truck carrier",
        "pctc",
        "автомобилевоз",
    ],
    "Multi-Purpose Vessel": [
        "multi-purpose vessel",
        "multipurpose vessel",
        "mpp vessel",
        "multi-purpose cargo ship",
        "multipurpose cargo ship",
        "multi-purpose general cargo vessel",
        "breakbulk/container vessel",
        "breakbulk container vessel",
        "general cargo mpp",
    ],
}

# Most specific first; broader categories come later so that e.g.
# "very large crude carrier" resolves to VLCC before Crude Oil Tanker,
# and "refrigerated cargo ship" resolves to Reefer before General Cargo.
FLEET_PRECEDENCE: tuple[str, ...] = (
    "VLCC",
    "Oil/Chemical Tanker",
    "Chemical Tanker",
    "Crude Oil Tanker",
    "LNG Carrier",
    "LPG Carrier",
    "Container Vessel",
    "Bulk Carrier",
    "Reefer",
    "Heavy-Lift Vessel",
    "Multi-Purpose Vessel",
    "General Cargo Vessel",
    "Tug",
    "Passenger Vessel",
    "Offshore Vessel",
    "Ro-Ro",
)

FLEET_INDEX: dict[str, int] = {name: i for i, name in enumerate(FLEET_PRECEDENCE)}

FLEET_OPTIONS: tuple[str, ...] = FLEET_PRECEDENCE


def _no_space_copy(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _expand_string_for_scan(raw: str) -> str:
    p = preprocess(raw)
    compact = _no_space_copy(p)
    return re.sub(r"\s+", " ", f"{p} {compact} {preprocess(p)}").strip().lower()


def _token_present(alias_lower: str, scan_lower: str) -> bool:
    if len(alias_lower) < 2:
        return False
    if re.search(rf"(?<![a-z0-9\u0400-\u04ff]){re.escape(alias_lower)}(?![a-z0-9\u0400-\u04ff])", scan_lower):
        return True
    return len(alias_lower) >= 4 and alias_lower in scan_lower


def _all_canons_matching_in_scan(scan: str) -> set[str]:
    found: set[str] = set()
    for canon, aliases in CANONICAL_ALIASES.items():
        for alias in (canon, *aliases):
            ap = preprocess(alias)
            if not ap or len(ap) < 2:
                continue
            if _token_present(ap, scan):
                found.add(canon)
                break
    return found


def resolve_canonical_fleet(raw: str) -> str | None:
    if not (raw or "").strip():
        return None
    scan = _expand_string_for_scan(raw)
    if not scan:
        return None
    matched = _all_canons_matching_in_scan(scan)
    if not matched:
        return None
    return min(matched, key=lambda c: FLEET_INDEX.get(c, 999))


def display_fleet_label(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    canon = resolve_canonical_fleet(text)
    return canon if canon else text


def _unique_terms_for_sql(strings: list[str], max_len: int = 500) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in strings:
        st = t.strip()[:max_len] if t else ""
        st = st.replace("%", "").replace("_", "")
        if not st:
            continue
        key = st.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(st)
    return out


def expand_canonical_fleet(canon: str) -> list[str]:
    aliases = [canon, *CANONICAL_ALIASES[canon]]
    extra: list[str] = []
    for alias in aliases:
        for variant in (alias, preprocess(alias), _no_space_copy(preprocess(alias))):
            cleaned = re.sub(r"\s+", " ", str(variant or "").strip())
            if cleaned:
                extra.append(cleaned)
    return _unique_terms_for_sql(extra)


def fleet_search_terms(user_input: str) -> list[str]:
    raw = (user_input or "").strip()
    if not raw:
        return []
    canon = resolve_canonical_fleet(raw)
    if canon:
        return expand_canonical_fleet(canon)
    return _unique_terms_for_sql([raw])


__all__ = [
    "CANONICAL_ALIASES",
    "FLEET_OPTIONS",
    "FLEET_PRECEDENCE",
    "display_fleet_label",
    "expand_canonical_fleet",
    "fleet_search_terms",
    "resolve_canonical_fleet",
]
