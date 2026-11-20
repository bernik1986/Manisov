const hasValue = value => value !== undefined && value !== null && value !== "";
const numberKey = value => String(value ?? "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");

export function makeDocument(files) {
  const types = new Set(files.map(file => file.type_key).filter(Boolean));
  const fields = {};
  const conflicts = [];
  for (const key of new Set(files.flatMap(file => Object.keys(file.fields ?? {})))) {
    const values = new Set(files.map(file => file.fields?.[key]).filter(hasValue));
    if (values.size === 1) fields[key] = [...values][0];
    if (values.size > 1) conflicts.push(key);
  }
  return {
    id: files[0].file_id, files, fields, conflicts,
    typeKey: types.size === 1 ? [...types][0] : "",
    action: "", existingId: "", existingVersion: "", confirmHolder: false, confirmTypeMismatch: false,
    error: files[0].error ?? "", saved: !!files[0].saved,
  };
}

export function documentsFromItems(items) {
  const groups = new Map();
  for (const file of items) {
    const key = !file.saved && !file.error && file.group_key
      ? `group:${file.group_key}` : `file:${file.file_id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(file);
  }
  return Array.from(groups.values(), makeDocument);
}

export function isReviewable(doc) {
  return !doc.saved && doc.files.every(file => file.content_type && !file.error);
}

export function hasHolderMismatch(doc) {
  return doc.error === "holder_mismatch"
    || doc.files.some(file => file.warnings?.includes("holder_mismatch"));
}

export function hasTypeMismatch(doc) {
  return doc.error === "type_hint_mismatch"
    || doc.files.some(file => file.warnings?.includes("type_hint_mismatch"));
}

export function findMatches(doc, existing) {
  const number = numberKey(doc.fields.number);
  const records = existing.filter(record => record.type_key === doc.typeKey);
  const exact = number ? records.filter(record => numberKey(record.fields.number) === number) : [];
  return {
    records, exact,
    canCreate: !exact.length,
    targets: exact.length ? exact : records,
  };
}

export function approvalFor(doc, spec, matches, individual = false) {
  if (doc.error === "save_outcome_unknown") return null;
  if (!isReviewable(doc) || !spec || spec.fields.some(key => doc.conflicts.includes(key)) || doc.action === "skip") return null;
  const mismatch = hasHolderMismatch(doc);
  if (mismatch && (!individual || !doc.confirmHolder)) return null;
  const typeMismatch = hasTypeMismatch(doc);
  if (typeMismatch && (!individual || !doc.confirmTypeMismatch)) return null;
  const action = doc.action || (matches.records.length ? "" : "create");
  const existing = matches.targets.find(record => String(record.id) === doc.existingId);
  const matchingVersion = existing?.version && existing.version === doc.existingVersion;
  if (!(action === "create" && matches.canCreate) && !(action === "update" && matchingVersion)) return null;
  const fields = Object.fromEntries(spec.fields
    .filter(key => hasValue(doc.fields[key]))
    .map(key => [key, doc.fields[key]]));
  return {
    file_ids: doc.files.map(file => file.file_id), type_key: spec.key, fields, action,
    existing_id: action === "update" ? existing.id : null, confirm_holder: mismatch && individual,
    ...(typeMismatch ? { confirm_type_mismatch: true } : {}),
    ...(action === "update" ? { existing_version: doc.existingVersion } : {}),
  };
}
