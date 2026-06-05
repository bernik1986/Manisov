/** Canonical diploma slots — keep in sync with `app/canonical_diplomas.py` */

export const DIPLOMA_GROUP = "Diploma";
export const TANKER_DIPLOMA_GROUP = "Tanker Diploma";

export const CANONICAL_DIPLOMA_SPECS = [
  { code: "COC", certificateType: "COC", group: DIPLOMA_GROUP, placeholderPrefix: "coc" },
  { code: "END_COC", certificateType: "Endorsement COC", group: DIPLOMA_GROUP, placeholderPrefix: "endorsement_coc" },
  { code: "COC_GMDSS", certificateType: "COC GMDSS", group: DIPLOMA_GROUP, placeholderPrefix: "coc_gmdss" },
  { code: "END_GMDSS", certificateType: "Endorsement GMDSS", group: DIPLOMA_GROUP, placeholderPrefix: "endorsement_gmdss" },
  { code: "COC_NAT", certificateType: "COC", group: DIPLOMA_GROUP, placeholderPrefix: "coc_national" },
  { code: "COP_WELDER", certificateType: "COP Ship's Welder", group: DIPLOMA_GROUP, placeholderPrefix: "cop_ships_welder" },
  { code: "COP_AB", certificateType: "COP Able Seafarer", group: DIPLOMA_GROUP, placeholderPrefix: "cop_able_seafarer" },
  { code: "COP_MOTO", certificateType: "COP Motorman", group: DIPLOMA_GROUP, placeholderPrefix: "cop_motorman" },
  { code: "COP_COOK", certificateType: "COP Ship's Cook", group: DIPLOMA_GROUP, placeholderPrefix: "cop_ships_cook" },
  { code: "COP_ELEC", certificateType: "COP Electrician", group: DIPLOMA_GROUP, placeholderPrefix: "cop_electrician" },
  { code: "COP", certificateType: "COP", group: DIPLOMA_GROUP, placeholderPrefix: "cop" },
];

export const CANONICAL_TANKER_DIPLOMA_SPECS = [
  { code: "T_BOC", certificateType: "COP Basic Oil&Chemical", group: TANKER_DIPLOMA_GROUP, placeholderPrefix: "cop_basic_oil_chemical" },
  { code: "T_ACC", certificateType: "COP Advanced Chemical", group: TANKER_DIPLOMA_GROUP, placeholderPrefix: "cop_advanced_chemical" },
  { code: "T_AOC", certificateType: "COP Advanced Oil", group: TANKER_DIPLOMA_GROUP, placeholderPrefix: "cop_advanced_oil" },
  { code: "T_BG", certificateType: "COP Basic Gas", group: TANKER_DIPLOMA_GROUP, placeholderPrefix: "cop_basic_gas" },
  { code: "T_AG", certificateType: "COP Advanced Gas", group: TANKER_DIPLOMA_GROUP, placeholderPrefix: "cop_advanced_gas" },
];

export const ALL_CANONICAL_DIPLOMA_SPECS = [...CANONICAL_DIPLOMA_SPECS, ...CANONICAL_TANKER_DIPLOMA_SPECS];

const ALL_DIPLOMA_SLOT_CODES = new Set(ALL_CANONICAL_DIPLOMA_SPECS.map((s) => s.code));

const NON_DIPLOMA_CERTIFICATE_GROUPS = new Set([
  "Conventional Certificate",
  "ECDIS Certificate",
  "Company Certificate",
  "BWTS Certificate",
]);

const LEGACY_SLOT_CODES = {
  COC: ["COC_END"],
  END_COC: ["COC_END"],
  COC_GMDSS: ["COC_GMDSS"],
  END_GMDSS: ["COC_GMDSS"],
  COC_NAT: ["COC"],
};

const MATCH_TERMS = {
  COC: ["certificate of competency", "competency", "competence"],
  END_COC: ["endorsement coc", "coc endorsement", "coc & endorsement", "coc and endorsement"],
  COC_GMDSS: ["coc gmdss", "gmdss", "radio operator"],
  END_GMDSS: ["endorsement gmdss", "gmdss endorsement", "coc gmdss & endorsement"],
  COC_NAT: ["ethiopian", "egyptian", "ukrainian coc", "national coc"],
  COP_WELDER: ["ship's welder", "ships welder", "welder", "ftr"],
  COP_AB: ["able seafarer", "able seaman"],
  COP_MOTO: ["motorman", "oiler"],
  COP_COOK: ["ship's cook", "ships cook"],
  COP_ELEC: ["electrician"],
  COP: ["certificate of proficiency", "cop "],
  T_BOC: ["basic oil", "oil & chemical", "oil and chemical", "oil/chemical"],
  T_ACC: ["advanced chemical"],
  T_AOC: ["advanced oil"],
  T_BG: ["basic gas"],
  T_AG: ["advanced gas"],
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
    if (specs.some((spec) => diplomaMatchesSpec(cert, spec))) {
      pool.push(cert);
    }
  }
  return pool;
}

export function diplomaMatchesSpec(cert, spec) {
  const group = String(cert.certificate_group || "").trim();
  if (NON_DIPLOMA_CERTIFICATE_GROUPS.has(group)) {
    return false;
  }
  const code = spec.code;
  const slotRaw = String(cert.certificate_name_raw || "").trim();
  const category = String(cert.certificate_code || "").trim();
  const dtype = String(cert.certificate_type || "").trim().toLowerCase();
  const canonical = String(spec.certificateType || "").trim().toLowerCase();
  const text = certHaystack(cert);

  if (slotRaw && slotRaw === code) return true;
  if (category && category === code) return true;
  if (category && category === spec.certificateType) return true;

  const legacySlots = LEGACY_SLOT_CODES[code] || [];
  if (slotRaw && legacySlots.includes(slotRaw)) {
    if (slotRaw === "COC_END") {
      if (code === "END_COC") return text.includes("endorsement");
      if (code === "COC") return !text.includes("endorsement");
    }
    if (slotRaw === "COC_GMDSS") {
      if (code === "END_GMDSS") return text.includes("endorsement");
      if (code === "COC_GMDSS") return !text.includes("endorsement");
    }
    if (slotRaw === "COC" && code === "COC_NAT") return true;
  }

  if (code === "COC") {
    if (text.includes("endorsement") && !text.includes("competency") && !text.includes("competence")) return false;
    if (text.includes("gmdss")) return false;
    if ((MATCH_TERMS.COC || []).some((term) => text.includes(term))) return true;
    return dtype === canonical;
  }
  if (code === "END_COC") {
    if (text.includes("gmdss")) return false;
    return (MATCH_TERMS.END_COC || []).some((term) => text.includes(term));
  }
  if (code === "COC_GMDSS") {
    if (text.includes("endorsement")) return false;
    return (MATCH_TERMS.COC_GMDSS || []).some((term) => text.includes(term));
  }
  if (code === "END_GMDSS") {
    return (MATCH_TERMS.END_GMDSS || []).some((term) => text.includes(term));
  }
  if (code === "COC_NAT") {
    if (text.includes("gmdss")) return false;
    if (text.includes("competency") || text.includes("competence")) return false;
    if (text.includes("endorsement")) return false;
    if (dtype === canonical) return (MATCH_TERMS.COC_NAT || []).some((term) => text.includes(term));
    return (MATCH_TERMS.COC_NAT || []).some((term) => text.includes(term));
  }
  if (code === "COP") {
    for (const other of CANONICAL_DIPLOMA_SPECS) {
      if (other.code === "COP") continue;
      if (text.includes(other.certificateType.toLowerCase())) return false;
    }
    return (MATCH_TERMS.COP || []).some((term) => text.includes(term));
  }
  return (MATCH_TERMS[code] || []).some((term) => text.includes(term));
}

export function isCustomDiplomaRow(item, specs) {
  const id = item?.certificate_id;
  if (id == null || item?.is_canonical_placeholder) {
    return false;
  }
  return !specs.some((spec) => diplomaMatchesSpec(item, spec));
}

function getId(item, keys) {
  for (const key of keys) {
    if (item?.[key] != null) return item[key];
  }
  return null;
}

export function findCanonicalDiplomaSpec(item, specs = ALL_CANONICAL_DIPLOMA_SPECS) {
  const slotId = String(item.diploma_code || item.certificate_name_raw || "").trim();
  if (slotId) {
    const bySlot = specs.find((spec) => spec.code === slotId);
    if (bySlot) return bySlot;
  }
  return specs.find((spec) => diplomaMatchesSpec(item, spec)) || null;
}

/** Код и тип диплома в UI — одно и то же человекочитаемое название. */
export function diplomaRowLabel(item, specs = ALL_CANONICAL_DIPLOMA_SPECS) {
  if (item.display_type) return String(item.display_type).trim();
  if (item.display_code) return String(item.display_code).trim();
  const spec = findCanonicalDiplomaSpec(item, specs);
  if (spec) return spec.certificateType;
  const dtype = String(item.certificate_type || "").trim();
  if (dtype) return dtype;
  return String(item.certificate_code || "").trim();
}

export function diplomaRowCode(item, specs = ALL_CANONICAL_DIPLOMA_SPECS) {
  return diplomaRowLabel(item, specs);
}

export function diplomaRowType(item, specs = ALL_CANONICAL_DIPLOMA_SPECS) {
  return diplomaRowLabel(item, specs);
}

function enrichDiplomaRow(cert, spec, specs) {
  const label = spec ? spec.certificateType : diplomaRowLabel(cert, specs);
  return {
    ...cert,
    diploma_code: spec?.code ?? cert.diploma_code,
    certificate_name_raw: spec?.code ?? cert.certificate_name_raw,
    display_code: label,
    display_type: label,
  };
}

export function isCanonicalDiplomaPlaceholder(item) {
  return Boolean(item?.is_canonical_placeholder) || !getId(item, ["certificate_id"]);
}

export function isCanonicalDiplomaItem(item) {
  const slot = String(item?.certificate_name_raw || "").trim();
  if (ALL_DIPLOMA_SLOT_CODES.has(slot)) return true;
  const group = String(item?.certificate_group || "").trim();
  if (group === DIPLOMA_GROUP || group === TANKER_DIPLOMA_GROUP) return true;
  if (NON_DIPLOMA_CERTIFICATE_GROUPS.has(group)) return false;
  return ALL_CANONICAL_DIPLOMA_SPECS.some((spec) => diplomaMatchesSpec(item, spec));
}

/** Always returns exactly one row per canonical diploma spec. */
export function buildDiplomaDisplayList(apiItems, _extraCertificates, specs) {
  return orderDiplomasForDisplay(apiItems, specs);
}

export function orderDiplomasForDisplay(items, specs) {
  const remaining = poolForSpecs(items, specs);
  const ordered = [];
  const usedIds = new Set();

  for (const spec of specs) {
    const idx = remaining.findIndex((cert) => {
      const id = cert.certificate_id;
      if (id != null && usedIds.has(id)) return false;
      return diplomaMatchesSpec(cert, spec);
    });
    if (idx < 0) {
      ordered.push(
        enrichDiplomaRow(
          {
            certificate_id: null,
            certificate_code: spec.certificateType,
            certificate_type: spec.certificateType,
            certificate_group: spec.group,
            diploma_code: spec.code,
            is_canonical_placeholder: true,
          },
          spec,
          specs
        )
      );
      continue;
    }
    const cert = enrichDiplomaRow({ ...remaining.splice(idx, 1)[0], diploma_code: spec.code }, spec, specs);
    if (cert.certificate_id != null) usedIds.add(cert.certificate_id);
    ordered.push(cert);
  }

  return ordered;
}

export function isWorkingCocDiplomaRow(item) {
  const slot = String(item?.diploma_code || item?.certificate_name_raw || "").trim();
  return slot === "COC";
}

export function canonicalDiplomaPlaceholderLines() {
  const suffixes = ["certificate_number", "issue_date", "expiry_date", "issuing_authority", "country_of_issue"];
  return ALL_CANONICAL_DIPLOMA_SPECS.flatMap((spec) => {
    const lines = suffixes.map((suffix) => `{{ ${spec.placeholderPrefix}_${suffix} }}`);
    if (spec.code === "COC") {
      lines.push("{{ coc_competency_rank }}");
    }
    return lines;
  });
}
