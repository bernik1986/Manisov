/** Canonical document slots — keep in sync with `app/canonical_documents.py` */

export const CANONICAL_DOCUMENT_SPECS = [
  { code: "YF", documentType: "Yellow Fever", label: "Yellow Fever", placeholderPrefix: "yf" },
  { code: "TP Bio", documentType: "Travel Passport (Ukraine)", label: "Загран паспорт (Украина)", placeholderPrefix: "tp_bio" },
  { code: "TP", documentType: "Travel Passport", label: "Загран паспорт (другие страны)", placeholderPrefix: "tp" },
  { code: "SB", documentType: "Seaman's Book", label: "Seaman's Book", placeholderPrefix: "sb" },
  { code: "SS", documentType: "Sea Service Record", label: "Послужная", placeholderPrefix: "ss" },
  { code: "SID", documentType: "Seafarer Identity Document", label: "Удостоверение личности моряка", placeholderPrefix: "sid" },
  { code: "CP", documentType: "Civil Passport", label: "Гражданский паспорт", placeholderPrefix: "cp" },
  { code: "ID code", documentType: "Tax ID Code", label: "ИНН код", placeholderPrefix: "id_code" },
  { code: "ID card", documentType: "Biometric ID Card", label: "Биометрический гражданский паспорт", placeholderPrefix: "id_card" },
  { code: "Residence", documentType: "Residence Registration", label: "Прописка", placeholderPrefix: "residence" },
];

const MATCH_TERMS = {
  YF: ["yellow fever", "yf", "yellow fever vaccination"],
  "TP Bio": ["tp bio", "travel passport (ukraine)", "ukrainian travel passport", "загран паспорт украин"],
  TP: ["travel passport", "passport", "tp", "загран паспорт"],
  SB: ["seaman's book", "seaman book", "seafarer book", "sb"],
  SS: ["sea service record", "discharge book", "discharge", "послужн", "ss"],
  SID: ["seafarer identity", "seaman identity", "sid", "удостоверение личности моряка"],
  CP: ["civil passport", "national passport", "гражданский паспорт", "cp"],
  "ID code": ["tax id", "id code", "inn", "инн", "ид код"],
  "ID card": ["biometric id", "biometric passport", "id card", "биометрическ"],
  Residence: ["residence", "residence registration", "прописк", "registration"],
};

function documentHaystack(doc) {
  return [doc.document_category, doc.document_type, doc.document_name_raw].filter(Boolean).join(" ").toLowerCase();
}

export function documentMatchesSpec(doc, spec) {
  const code = spec.code;
  const category = String(doc.document_category || "").trim();
  const dtype = String(doc.document_type || "").trim().toLowerCase();
  const canonical = String(spec.documentType || "").trim().toLowerCase();

  if (category && category === code) return true;
  if (dtype && dtype === canonical) return true;

  const hay = documentHaystack(doc);
  if (code === "TP" && (dtype.includes("ukraine") || category === "TP Bio")) return false;
  if (code === "TP Bio") {
    return (MATCH_TERMS[code] || []).some((term) => hay.includes(term));
  }
  return (MATCH_TERMS[code] || []).some((term) => hay.includes(term));
}

export function findCanonicalSpecForRow(item) {
  const code = String(item.document_code || item.document_category || "").trim();
  if (code) {
    return CANONICAL_DOCUMENT_SPECS.find((spec) => spec.code === code) || null;
  }
  return CANONICAL_DOCUMENT_SPECS.find((spec) => documentMatchesSpec(item, spec)) || null;
}

export function orderDocumentsForDisplay(documents) {
  const remaining = [...(documents || [])];
  const ordered = [];
  const usedIds = new Set();

  for (const spec of CANONICAL_DOCUMENT_SPECS) {
    const idx = remaining.findIndex((doc) => {
      const id = doc.document_id;
      if (id != null && usedIds.has(id)) return false;
      return documentMatchesSpec(doc, spec);
    });
    if (idx < 0) {
      ordered.push({
        document_id: null,
        document_category: spec.code,
        document_type: spec.documentType,
        is_canonical_placeholder: true,
      });
      continue;
    }
    const doc = { ...remaining.splice(idx, 1)[0], document_code: spec.code };
    if (doc.document_id != null) usedIds.add(doc.document_id);
    ordered.push(doc);
  }

  for (const doc of remaining) {
    if (doc.document_id != null && usedIds.has(doc.document_id)) continue;
    ordered.push(doc);
  }
  return ordered;
}

export function canonicalDocumentPlaceholderLines() {
  const suffixes = ["document_number", "issue_date", "expiry_date", "issuing_authority", "place_of_issue"];
  return CANONICAL_DOCUMENT_SPECS.flatMap((spec) =>
    suffixes.map((suffix) => `{{ ${spec.placeholderPrefix}_${suffix} }}`)
  );
}
