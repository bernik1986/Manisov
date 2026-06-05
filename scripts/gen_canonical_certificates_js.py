"""Generate app/frontend/src/canonicalCertificates.js from Python specs."""

from __future__ import annotations

import json
from pathlib import Path

from app.canonical_certificates import (
    CANONICAL_BWTS_SPECS,
    CANONICAL_COMPANY_SPECS,
    CANONICAL_CONVENTIONAL_SPECS,
    CANONICAL_ECDIS_SPECS,
    ALL_CANONICAL_CERTIFICATE_SPECS,
)


def _to_js_specs(specs):
    rows = []
    for spec in specs:
        rows.append(
            {
                "code": spec["code"],
                "displayCode": spec.get("display_code", spec["code"]),
                "displayType": spec.get("display_type", spec.get("certificate_type", spec["code"])),
                "certificateType": spec.get("display_type", spec.get("certificate_type", spec["code"])),
                "group": spec["certificate_group"],
                "placeholderPrefix": spec["placeholder_prefix"],
                "matchTerms": list(spec["match_terms"]),
            }
        )
    return rows


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "app" / "frontend" / "src" / "canonicalCertificates.js"
    payload = {
        "conventional": _to_js_specs(CANONICAL_CONVENTIONAL_SPECS),
        "ecdis": _to_js_specs(CANONICAL_ECDIS_SPECS),
        "company": _to_js_specs(CANONICAL_COMPANY_SPECS),
        "bwts": _to_js_specs(CANONICAL_BWTS_SPECS),
        "all": _to_js_specs(ALL_CANONICAL_CERTIFICATE_SPECS),
    }
    js = f"""/** Auto-synced from `app/canonical_certificates.py` — run scripts/gen_canonical_certificates_js.py */

export const CONVENTIONAL_GROUP = "Conventional Certificate";
export const ECDIS_GROUP = "ECDIS Certificate";
export const COMPANY_GROUP = "Company Certificate";
export const BWTS_GROUP = "BWTS Certificate";

export const CANONICAL_CONVENTIONAL_SPECS = {json.dumps(payload["conventional"], ensure_ascii=False, indent=2)};

export const CANONICAL_ECDIS_SPECS = {json.dumps(payload["ecdis"], ensure_ascii=False, indent=2)};

export const CANONICAL_COMPANY_SPECS = {json.dumps(payload["company"], ensure_ascii=False, indent=2)};

export const CANONICAL_BWTS_SPECS = {json.dumps(payload["bwts"], ensure_ascii=False, indent=2)};

export const ALL_CANONICAL_CERTIFICATE_SPECS = {json.dumps(payload["all"], ensure_ascii=False, indent=2)};

function certHaystack(cert) {{
  return [
    cert.certificate_code,
    cert.certificate_type,
    cert.certificate_name_raw,
    cert.certificate_group,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}}

export function certificateMatchesSpec(cert, spec) {{
  const slotId = spec.code;
  const category = String(cert.certificate_code || "").trim();
  const nameRaw = String(cert.certificate_name_raw || "").trim();
  const dtype = String(cert.certificate_type || "").trim().toLowerCase();
  const displayCode = String(spec.displayCode || "").trim();
  const displayType = String(spec.displayType || "").trim().toLowerCase();
  const text = certHaystack(cert);

  if (nameRaw && nameRaw === slotId) return true;
  if (category && category === slotId) return true;
  if (displayCode && category === displayCode) return true;
  if (dtype && displayType && dtype === displayType) return true;
  return (spec.matchTerms || []).some((term) => text.includes(term));
}}

export function findCanonicalCertificateSpec(item, specs = ALL_CANONICAL_CERTIFICATE_SPECS) {{
  const slot = String(item.certificate_slot_code || item.certificate_name_raw || "").trim();
  if (slot) {{
    const bySlot = specs.find((spec) => spec.code === slot);
    if (bySlot) return bySlot;
  }}
  const code = String(item.certificate_code || "").trim();
  if (code) {{
    const byCode = specs.find((spec) => spec.code === code || spec.displayCode === code);
    if (byCode) return byCode;
  }}
  return specs.find((spec) => certificateMatchesSpec(item, spec)) || null;
}}

export function certificateRowCode(item) {{
  if (item.display_code) return item.display_code;
  const spec = findCanonicalCertificateSpec(item);
  if (spec) return spec.displayCode;
  return item.certificate_code || "";
}}

export function certificateRowType(item) {{
  if (item.display_type) return item.display_type;
  const spec = findCanonicalCertificateSpec(item);
  if (spec) return spec.displayType;
  return item.certificate_type || "";
}}

export function isCanonicalCertificateItem(item) {{
  return ALL_CANONICAL_CERTIFICATE_SPECS.some((spec) => certificateMatchesSpec(item, spec));
}}

export function orderCertificatesForDisplay(items, specs) {{
  const remaining = [...(items || [])];
  const ordered = [];
  const usedIds = new Set();

  for (const spec of specs) {{
    const idx = remaining.findIndex((cert) => {{
      const id = cert.certificate_id;
      if (id != null && usedIds.has(id)) return false;
      return certificateMatchesSpec(cert, spec);
    }});
    if (idx < 0) {{
      ordered.push({{
        certificate_id: null,
        certificate_code: spec.displayCode,
        certificate_type: spec.displayType,
        certificate_name_raw: spec.code,
        certificate_group: spec.group,
        certificate_slot_code: spec.code,
        display_code: spec.displayCode,
        display_type: spec.displayType,
        is_canonical_placeholder: true,
      }});
      continue;
    }}
    const cert = {{
      ...remaining.splice(idx, 1)[0],
      certificate_slot_code: spec.code,
      display_code: spec.displayCode,
      display_type: spec.displayType,
    }};
    if (cert.certificate_id != null) usedIds.add(cert.certificate_id);
    ordered.push(cert);
  }}
  return ordered;
}}

export function buildCertificateDisplayList(apiItems, extraCertificates, specs) {{
  const pool = [...(apiItems || [])];
  for (const cert of extraCertificates || []) {{
    if (!cert) continue;
    const id = cert.certificate_id;
    if (id != null && pool.some((row) => row.certificate_id === id)) continue;
    if (specs.some((spec) => certificateMatchesSpec(cert, spec))) {{
      pool.push(cert);
    }}
  }}
  return orderCertificatesForDisplay(pool, specs);
}}

export function canonicalCertificatePlaceholderLines() {{
  const suffixes = ["certificate_number", "issue_date", "expiry_date", "issuing_authority", "country_of_issue"];
  return ALL_CANONICAL_CERTIFICATE_SPECS.flatMap((spec) =>
    suffixes.map((suffix) => `{{ ${{spec.placeholderPrefix}}_${{suffix}} }}`)
  );
}}
"""
    out.write_text(js, encoding="utf-8")
    print(f"Wrote {out} ({len(payload['all'])} specs)")


if __name__ == "__main__":
    main()
