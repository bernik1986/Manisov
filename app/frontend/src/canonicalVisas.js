/** Canonical visa slots — keep in sync with `app/canonical_visas.py` */

export const CANONICAL_VISA_SPECS = [
  { code: "Visa USA", documentType: "Visa USA", placeholderPrefix: "usa_visa" },
  { code: "Australian Maritime Crew Visa", documentType: "Australian Maritime Crew Visa", placeholderPrefix: "mcv" },
  { code: "Visa Canada", documentType: "Visa Canada", placeholderPrefix: "visa_canada" },
  { code: "Visa Schengen", documentType: "Visa Schengen", placeholderPrefix: "visa_schengen" },
  { code: "Visa China", documentType: "Visa China", placeholderPrefix: "visa_china" },
  { code: "Visa Brazil", documentType: "Visa Brazil", placeholderPrefix: "visa_brazil" },
  { code: "Visa Fujairah", documentType: "Visa Fujairah", placeholderPrefix: "visa_fujairah" },
  { code: "Visa Taiwan", documentType: "Visa Taiwan", placeholderPrefix: "visa_taiwan" },
  { code: "Visa Indonesia", documentType: "Visa Indonesia", placeholderPrefix: "visa_indonesia" },
  { code: "Australian Transit Visa", documentType: "Australian Transit Visa", placeholderPrefix: "visa_australian_transit" },
  { code: "Visa India", documentType: "Visa India", placeholderPrefix: "visa_india" },
  { code: "Visa Thailand", documentType: "Visa Thailand", placeholderPrefix: "visa_thailand" },
];

const LEGACY_VISA_CATEGORIES = {
  MCV: "Australian Maritime Crew Visa",
  "Visa USA": "Visa USA",
};

const MATCH_TERMS = {
  "Visa USA": ["usa visa", "us visa", "american visa", "visa usa"],
  "Australian Maritime Crew Visa": [
    "australian maritime crew visa",
    "maritime crew visa (australia)",
    "maritime crew visa",
    "mcv",
    "australia crew visa",
    "crew visa australia",
  ],
  "Visa Canada": ["visa canada", "canada visa", "canadian visa"],
  "Visa Schengen": ["visa schengen", "schengen visa"],
  "Visa China": ["visa china", "china visa", "chinese visa"],
  "Visa Brazil": ["visa brazil", "brazil visa", "brazilian visa"],
  "Visa Fujairah": ["visa fujairah", "fujairah visa"],
  "Visa Taiwan": ["visa taiwan", "taiwan visa"],
  "Visa Indonesia": ["visa indonesia", "indonesia visa", "indonesian visa"],
  "Australian Transit Visa": ["australian transit visa", "transit visa australia", "australia transit visa"],
  "Visa India": ["visa india", "india visa", "indian visa"],
  "Visa Thailand": ["visa thailand", "thailand visa", "thai visa"],
};

function documentHaystack(doc) {
  return [doc.document_category, doc.document_type, doc.document_name_raw].filter(Boolean).join(" ").toLowerCase();
}

export function visaMatchesSpec(doc, spec) {
  const code = spec.code;
  const category = String(doc.document_category || "").trim();
  const dtype = String(doc.document_type || "").trim().toLowerCase();
  const canonical = String(spec.documentType || "").trim().toLowerCase();

  if (category && category === code) return true;
  if (category && LEGACY_VISA_CATEGORIES[category] === code) return true;
  if (dtype && dtype === canonical) return true;
  const hay = documentHaystack(doc);
  return (MATCH_TERMS[code] || []).some((term) => hay.includes(term));
}

export function findCanonicalVisaSpecForRow(item) {
  const code = String(item.visa_code || item.document_category || "").trim();
  if (code) {
    return CANONICAL_VISA_SPECS.find((spec) => spec.code === code) || null;
  }
  return CANONICAL_VISA_SPECS.find((spec) => visaMatchesSpec(item, spec)) || null;
}

export function isCanonicalVisaRow(item) {
  return Boolean(findCanonicalVisaSpecForRow(item));
}

export function isCustomVisaRow(item) {
  if (item?.is_canonical_placeholder) return false;
  if (item?.document_id == null) return false;
  return !isCanonicalVisaRow(item);
}

export function visaRowCode(item) {
  return item.visa_code || item.document_category || findCanonicalVisaSpecForRow(item)?.code || "";
}

function visaRowHasData(doc) {
  return Boolean(
    String(doc.document_number || "").trim() ||
      doc.date_of_issue ||
      doc.date_of_expiry ||
      String(doc.scan_file || "").trim()
  );
}

function pickPrimaryVisaRow(matches) {
  const withData = matches.filter(visaRowHasData);
  const pool = withData.length ? withData : matches;
  return pool.reduce((best, row) =>
    (row.document_id ?? 0) < (best.document_id ?? 0) ? row : best
  );
}

export function visaMatchesAnyCanonicalSpec(doc) {
  return CANONICAL_VISA_SPECS.some((spec) => visaMatchesSpec(doc, spec));
}

/** One row per canonical visa; drop duplicate legacy/parser rows. */
export function orderVisasForDisplay(visas) {
  const remaining = [...(visas || [])];
  const ordered = [];
  const usedIds = new Set();

  for (const spec of CANONICAL_VISA_SPECS) {
    const matches = remaining.filter((doc) => {
      const id = doc.document_id;
      if (id != null && usedIds.has(id)) return false;
      return visaMatchesSpec(doc, spec);
    });
    if (!matches.length) {
      if (!remaining.some((doc) => doc.visa_code === spec.code && doc.document_id != null)) {
        ordered.push({
          document_id: null,
          document_category: spec.code,
          document_type: spec.documentType,
          visa_code: spec.code,
          is_canonical_placeholder: true,
        });
      }
      continue;
    }
    const primary = pickPrimaryVisaRow(matches);
    const matchIds = new Set(matches.map((row) => row.document_id).filter((id) => id != null));
    for (let i = remaining.length - 1; i >= 0; i -= 1) {
      if (matchIds.has(remaining[i].document_id)) {
        remaining.splice(i, 1);
      }
    }
    const doc = { ...primary, visa_code: spec.code };
    if (doc.document_id != null) usedIds.add(doc.document_id);
    ordered.push(doc);
  }

  for (const doc of remaining) {
    if (doc.document_id != null && usedIds.has(doc.document_id)) continue;
    if (visaMatchesAnyCanonicalSpec(doc)) continue;
    const code = String(doc.document_category || doc.document_type || "").trim();
    if (!code.toLowerCase().includes("visa")) continue;
    ordered.push({ ...doc, visa_code: code });
    if (doc.document_id != null) usedIds.add(doc.document_id);
  }
  return ordered;
}

export function canonicalVisaPlaceholderLines() {
  const suffixes = [
    "document_number",
    "issue_date",
    "expiry_date",
    "issuing_authority",
    "place_of_issue",
    "visa_code",
    "visa_name",
  ];
  return CANONICAL_VISA_SPECS.flatMap((spec) =>
    suffixes.map((suffix) => `{{ ${spec.placeholderPrefix}_${suffix} }}`)
  );
}
