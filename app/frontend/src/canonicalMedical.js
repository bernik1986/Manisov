/** Canonical medical document slots — keep in sync with `app/canonical_medical.py` */

export const MEDICAL_GROUP = "Medical Document";

export const CANONICAL_MEDICAL_SPECS = [
  { code: "COVID", certificateType: "Covid Certificate", group: MEDICAL_GROUP, placeholderPrefix: "covid_certificate" },
  { code: "MED_EXAM", certificateType: "Medical Examination", group: MEDICAL_GROUP, placeholderPrefix: "medical_examination" },
  { code: "HEP_B", certificateType: "Hepatitis vaccination", group: MEDICAL_GROUP, placeholderPrefix: "hepatitis_vaccination" },
];

const ALL_MEDICAL_SLOT_CODES = new Set(CANONICAL_MEDICAL_SPECS.map((s) => s.code));

const NON_MEDICAL_CERTIFICATE_GROUPS = new Set([
  "Conventional Certificate",
  "ECDIS Certificate",
  "Company Certificate",
  "BWTS Certificate",
  "Diploma",
  "Tanker Diploma",
]);

const STCW_MEDICAL_TRAINING_TERMS = [
  "medical first aid",
  "medical care",
  "craft and rb medical",
  "proficiency in medical",
];

const MATCH_TERMS = {
  COVID: ["covid certificate", "covid-19", "covid 19", "covid vaccination", "coronavirus", "vaccination covid"],
  MED_EXAM: ["medical examination", "medical exam", "seafarer medical", "medical fitness", "ilo medical", "medical certificate", "medical report"],
  HEP_B: ["hepatitis vaccination", "hepatitis vaccine", "hepatitis b", "hep b", "hepatitis"],
};

function certHaystack(cert) {
  return [
    cert.certificate_code,
    cert.certificate_type,
    cert.certificate_name_raw,
    cert.certificate_group,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function poolForSpecs(certificates, specs) {
  const specCodes = new Set(specs.map((s) => s.code));
  const groups = new Set(specs.map((s) => s.group));
  const pool = [];
  for (const cert of certificates || []) {
    const raw = String(cert.certificate_name_raw || "").trim();
    if (specCodes.has(raw)) {
      pool.push(cert);
      continue;
    }
    const group = String(cert.certificate_group || "").trim();
    if (groups.has(group)) {
      pool.push(cert);
      continue;
    }
    if (specs.some((spec) => medicalMatchesSpec(cert, spec))) {
      pool.push(cert);
    }
  }
  return pool;
}

export function medicalMatchesSpec(cert, spec) {
  const group = String(cert.certificate_group || "").trim();
  if (NON_MEDICAL_CERTIFICATE_GROUPS.has(group)) {
    return false;
  }
  const code = spec.code;
  const slotRaw = String(cert.certificate_name_raw || "").trim();
  const category = String(cert.certificate_code || "").trim();
  const dtype = String(cert.certificate_type || "").trim().toLowerCase();
  const canonical = String(spec.certificateType || "").trim().toLowerCase();
  const text = certHaystack(cert);

  if (STCW_MEDICAL_TRAINING_TERMS.some((term) => text.includes(term))) {
    return false;
  }

  if (slotRaw && slotRaw === code) return true;
  if (category && category === code) return true;
  if (category && category === spec.certificateType) return true;
  if (dtype && dtype === canonical) return true;

  if (code === "MED_EXAM") {
    if (text.includes("first aid") || text.includes("medical care")) return false;
    return (MATCH_TERMS.MED_EXAM || []).some((term) => text.includes(term));
  }
  if (code === "HEP_B") {
    if (text.includes("covid")) return false;
    return (MATCH_TERMS.HEP_B || []).some((term) => text.includes(term));
  }
  if (code === "COVID") {
    return (MATCH_TERMS.COVID || []).some((term) => text.includes(term));
  }
  return (MATCH_TERMS[code] || []).some((term) => text.includes(term));
}

export function isCustomMedicalRow(item, specs = CANONICAL_MEDICAL_SPECS) {
  const id = item?.certificate_id;
  if (id == null || item?.is_canonical_placeholder) {
    return false;
  }
  return !specs.some((spec) => medicalMatchesSpec(item, spec));
}

export function findCanonicalMedicalSpec(item, specs = CANONICAL_MEDICAL_SPECS) {
  const slotId = String(item.medical_code || item.diploma_code || item.certificate_name_raw || "").trim();
  if (slotId) {
    const bySlot = specs.find((spec) => spec.code === slotId);
    if (bySlot) return bySlot;
  }
  return specs.find((spec) => medicalMatchesSpec(item, spec)) || null;
}

export function medicalRowLabel(item, specs = CANONICAL_MEDICAL_SPECS) {
  if (item.display_type) return String(item.display_type).trim();
  if (item.display_code) return String(item.display_code).trim();
  const spec = findCanonicalMedicalSpec(item, specs);
  if (spec) return spec.certificateType;
  const dtype = String(item.certificate_type || "").trim();
  if (dtype) return dtype;
  return String(item.certificate_code || "").trim();
}

export function medicalRowCode(item, specs = CANONICAL_MEDICAL_SPECS) {
  return medicalRowLabel(item, specs);
}

export function medicalRowType(item, specs = CANONICAL_MEDICAL_SPECS) {
  return medicalRowLabel(item, specs);
}

function enrichMedicalRow(cert, spec, specs) {
  const label = spec ? spec.certificateType : medicalRowLabel(cert, specs);
  return {
    ...cert,
    medical_code: spec?.code ?? cert.medical_code,
    diploma_code: spec?.code ?? cert.diploma_code ?? cert.certificate_name_raw,
    certificate_name_raw: spec?.code ?? cert.certificate_name_raw,
    display_code: label,
    display_type: label,
  };
}

export function buildMedicalDisplayList(apiItems, _extraCertificates, specs = CANONICAL_MEDICAL_SPECS) {
  return orderMedicalForDisplay(apiItems, specs);
}

export function orderMedicalForDisplay(items, specs) {
  const remaining = poolForSpecs(items, specs);
  const ordered = [];
  const usedIds = new Set();

  for (const spec of specs) {
    const idx = remaining.findIndex((cert) => {
      const id = cert.certificate_id;
      if (id != null && usedIds.has(id)) return false;
      return medicalMatchesSpec(cert, spec);
    });
    if (idx < 0) {
      ordered.push(
        enrichMedicalRow(
          {
            certificate_id: null,
            certificate_code: spec.certificateType,
            certificate_type: spec.certificateType,
            certificate_group: spec.group,
            medical_code: spec.code,
            is_canonical_placeholder: true,
          },
          spec,
          specs
        )
      );
      continue;
    }
    const cert = enrichMedicalRow({ ...remaining.splice(idx, 1)[0], medical_code: spec.code }, spec, specs);
    if (cert.certificate_id != null) usedIds.add(cert.certificate_id);
    ordered.push(cert);
  }

  return ordered;
}

export function canonicalMedicalPlaceholderLines() {
  const suffixes = ["certificate_number", "issue_date", "expiry_date", "issuing_authority", "country_of_issue"];
  return CANONICAL_MEDICAL_SPECS.flatMap((spec) =>
    suffixes.map((suffix) => `{{ ${spec.placeholderPrefix}_${suffix} }}`)
  );
}
