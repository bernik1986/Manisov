import { documentsFromItems, isReviewable, makeDocument } from "./documentIntake.js";

const PREFIX = "parcer:intake-review:v1:";
const SESSION_KEY = "parcer:intake-review-session:v1";
const SEVEN_DAYS = 7 * 24 * 60 * 60 * 1000;
const fileIds = doc => doc.files.map(file => file.file_id);
const reviewFields = ["typeKey", "action", "existingId", "existingVersion"];
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
let activeSession = null;

export function reviewDraftKey(user, candidateId) {
  const account = user?.user_id ?? user?.username;
  return account == null ? "" : PREFIX + JSON.stringify([account, String(candidateId)]);
}

export function clearReviewDrafts() {
  try {
    for (const key of Object.keys(sessionStorage).filter(key => key.startsWith(PREFIX))) {
      sessionStorage.removeItem(key);
    }
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Storage is unavailable.
  }
}

export function setReviewDraftSession(session) {
  activeSession = session || "";
  return syncReviewDraftSession(activeSession);
}

export function syncReviewDraftSession(session) {
  session = session || "";
  // A detached review must not restore its old session after logout/switch.
  if (activeSession !== null && activeSession !== session) return false;
  try {
    if (sessionStorage.getItem(SESSION_KEY) !== session) {
      clearReviewDrafts();
      if (session) sessionStorage.setItem(SESSION_KEY, session);
    }
    return Boolean(session);
  } catch {
    return false;
  }
}

export function readReviewDrafts(scope, now = Date.now()) {
  if (!scope || activeSession === "") return {};
  try {
    let drafts = {};
    for (const storageKey of Object.keys(sessionStorage).filter(key => key.startsWith(PREFIX))) {
      let data;
      try {
        data = JSON.parse(sessionStorage.getItem(storageKey));
      } catch {
        data = null;
      }
      const valid = Object.fromEntries(Object.entries(data ?? {}).filter(([, value]) => value?.expiresAt > now));
      if (!Object.keys(valid).length) sessionStorage.removeItem(storageKey);
      else if (Object.keys(valid).length !== Object.keys(data).length) {
        sessionStorage.setItem(storageKey, JSON.stringify(valid));
      }
      if (storageKey === scope) drafts = valid;
    }
    return drafts;
  } catch {
    return {};
  }
}

export function writeReviewDrafts(scope, batches, visibleBatchIds, now = Date.now()) {
  if (!scope || activeSession === "") return false;
  try {
    const drafts = readReviewDrafts(scope, now);
    if (visibleBatchIds) {
      for (const id of Object.keys(drafts)) {
        if (!visibleBatchIds.includes(id)) delete drafts[id];
      }
    }
    for (const batch of batches) {
      if (batch.processed < batch.total) continue;
      const documents = batch.documents.filter(isReviewable);
      const autoGroups = documentsFromItems(batch.items).map(fileIds);
      const changes = [];
      for (const doc of documents) {
        const ids = fileIds(doc);
        const baseline = makeDocument(doc.files);
        const fields = Object.fromEntries(Object.entries(doc.fields).filter(([key, value]) =>
          !Object.is(baseline.fields[key], value)));
        const review = Object.fromEntries(reviewFields.filter(key => !Object.is(doc[key], baseline[key]))
          .map(key => [key, doc[key]]));
        const conflicts = same(doc.conflicts, baseline.conflicts) ? undefined : doc.conflicts;
        if (Object.keys(fields).length || Object.keys(review).length || conflicts ||
            !autoGroups.some(group => same(group, ids))) {
          changes.push({ ids, fields, review, conflicts });
        }
      }
      const expiresAt = Math.min(drafts[batch.id]?.expiresAt ?? Infinity, batch.expiresAt);
      if (changes.length && expiresAt > now) drafts[batch.id] = { expiresAt, changes };
      else delete drafts[batch.id];
    }
    if (Object.keys(drafts).length) sessionStorage.setItem(scope, JSON.stringify(drafts));
    else sessionStorage.removeItem(scope);
    return true;
  } catch {
    return false;
  }
}

export function reviewDraftDeadline(batch, previous, now = Date.now()) {
  const expiresAt = Date.parse(batch.expires_at);
  const createdAt = Date.parse(batch.created_at);
  return Math.min(previous ?? Infinity, Number.isFinite(expiresAt) ? expiresAt
    : (Number.isFinite(createdAt) ? createdAt : now) + SEVEN_DAYS);
}

export function restoreReviewDraft(items, persisted) {
  if (!Array.isArray(persisted?.changes)) return documentsFromItems(items);
  const reviewable = new Map(items.filter(file => isReviewable(makeDocument([file])))
    .map(file => [file.file_id, file]));
  const restored = [];
  for (const change of persisted.changes) {
    if (!Array.isArray(change?.ids) || !change.review || !change.fields) continue;
    const files = change.ids.map(id => reviewable.get(id));
    if (!files.length || files.some(file => !file)) continue;
    const baseline = makeDocument(files);
    const review = Object.fromEntries(reviewFields.filter(key => Object.hasOwn(change.review, key))
      .map(key => [key, change.review[key]]));
    restored.push({
      ...baseline, ...review,
      fields: { ...baseline.fields, ...change.fields },
      conflicts: change.conflicts ?? baseline.conflicts,
    });
    files.forEach(file => reviewable.delete(file.file_id));
  }
  const restoredByFile = new Map(restored.flatMap(doc => doc.files.map(file => [file.file_id, doc])));
  const remaining = documentsFromItems(items.filter(file => !restoredByFile.has(file.file_id)));
  const order = new Map(items.map((file, index) => [file.file_id, index]));
  const firstIndex = doc => Math.min(...fileIds(doc).map(id => order.get(id)));
  return [...restored, ...remaining].sort((left, right) => firstIndex(left) - firstIndex(right));
}
