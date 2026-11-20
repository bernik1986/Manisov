import React, { useEffect, useRef, useState } from "react";
import catalog from "../utils/documentIntakeLabels.js";
import {
  discardIntake, fetchIntake, fetchIntakePreview, fetchIntakeStatus, recognizeIntakeSubmission,
  retryIntake, saveIntake, uploadIntake,
} from "../documentIntakeApi.js";
import { approvalFor, documentsFromItems, findMatches, hasHolderMismatch, hasTypeMismatch, isReviewable, makeDocument } from "../utils/documentIntake.js";
import { readReviewDrafts, restoreReviewDraft, reviewDraftDeadline, reviewDraftKey, syncReviewDraftSession, writeReviewDrafts } from "../utils/documentIntakeDrafts.js";
import { reviewDraftSession } from "../api.js";
import { useAuth } from "../context/AuthContext";
import CandidateUploadControls from "./CandidateUploadControls.jsx";
import "./DocumentIntake.css";

const key = code => `intake.${code}`;
const allowedPreviewTypes = new Set(["image/jpeg", "image/png"]);
const isDate = name => name === "issue_date" || name === "expiry_date";
const MAX_FILES = 40;
const MAX_BATCH_BYTES = 45 * 1024 * 1024;
const t = (id, params = {}) => (catalog[id] ?? id).replace(/\{(\w+)\}/g, (_, name) => params[name] ?? "");
const label = (t, code, params) => t(key(code), params);
const errorLabel = (t, code) => label(t, Object.hasOwn(catalog, key(code)) ? code : "requestFailed");

function requestCode(error, fallback) {
  if (error?.response?.status === 403) return "forbidden";
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" && Object.hasOwn(catalog, key(detail)) ? detail : fallback;
}

function mergeRemoteBatches(local, remote, drafts = {}) {
  return remote.map(batch => {
    const previous = local.find(item => item.id === batch.batch_id);
    const metadata = {
      id: batch.batch_id,
      name: batch.name ?? batch.items[0]?.name,
      processed: batch.processed ?? batch.items.length,
      total: batch.total ?? batch.items.length,
      external: batch.external ?? previous?.external ?? false,
      expiresAt: reviewDraftDeadline(batch, previous?.expiresAt ?? drafts[batch.batch_id]?.expiresAt),
      items: batch.items,
    };
    if (metadata.processed < metadata.total) return { ...metadata, documents: previous?.documents ?? [] };
    if (!previous?.documents.length) {
      return { ...metadata, documents: restoreReviewDraft(batch.items, drafts[batch.batch_id]) };
    }
    const byId = new Map(batch.items.map(item => [item.file_id, item]));
    const keep = previous.documents.filter(doc =>
      doc.files.every(file => {
        const next = byId.get(file.file_id);
        return next && Boolean(next.saved) === doc.saved && next.error === file.error
          && Boolean(next.retryable) === Boolean(file.retryable);
      })
    ).map(doc => {
      const files = doc.files.map(file => byId.get(file.file_id));
      const warningChanged = files.some((file, index) =>
        JSON.stringify(file.warnings) !== JSON.stringify(doc.files[index].warnings));
      return { ...doc, files, ...(warningChanged ? { confirmHolder: false, confirmTypeMismatch: false } : {}) };
    });
    const preserved = new Set(keep.flatMap(doc => doc.files.map(file => file.file_id)));
    return { ...metadata, documents: [...keep, ...documentsFromItems(batch.items.filter(file => !preserved.has(file.file_id)))] };
  });
}

function ScanPreview({ candidateId, batchId, file, t }) {
  const scan = useRef(null);
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [preview, setPreview] = useState(null);
  const [zoom, setZoom] = useState(false);
  const pages = file.content_type === "application/pdf" ? Math.max(1, file.page_count || 1) : 1;
  useEffect(() => {
    const controller = new AbortController();
    let url;
    setPreview(null);
    fetchIntakePreview(candidateId, batchId, file.file_id, page, controller.signal)
      .then(blob => {
        if (controller.signal.aborted) return;
        if (!allowedPreviewTypes.has(blob.type)) throw new Error("Invalid preview media type");
        url = URL.createObjectURL(blob);
        setPreview({ url, page, retry });
      })
      .catch(() => {
        if (!controller.signal.aborted) setPreview({ page, retry, error: true });
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [candidateId, batchId, file.file_id, page, retry]);

  useEffect(() => {
    scan.current?.scrollTo(0, 0);
  }, [page, zoom]);

  const current = preview?.page === page && preview?.retry === retry ? preview : null;
  return (
    <>
      <div className="intake-preview-controls">
        {pages > 1 && (
          <div className="intake-page-controls">
            <button type="button" className="secondary-btn" disabled={page === 1} onClick={() => setPage(page - 1)}>
              {label(t, "previous")}
            </button>
            <span aria-live="polite">{label(t, "page", { page, total: pages })}</span>
            <button type="button" className="secondary-btn" disabled={page === pages} onClick={() => setPage(page + 1)}>
              {label(t, "next")}
            </button>
          </div>
        )}
        <button type="button" className="secondary-btn" disabled={!current?.url} aria-pressed={zoom} onClick={() => setZoom(value => !value)}>
          {label(t, zoom ? "fit" : "zoom")}
        </button>
      </div>
      <div ref={scan} className={`intake-scan${zoom ? " intake-scan-zoom" : ""}`}
        role="region" aria-label={label(t, "original")} tabIndex={zoom ? 0 : undefined}>
        {current?.url ? <img src={current.url} alt={file.name} onError={() => setPreview({ page, retry, error: true })} /> : current?.error ? (
          <div>
            <p role="alert">{label(t, "previewFailed")}</p>
            <button type="button" className="secondary-btn" onClick={() => setRetry(retry + 1)}>{label(t, "retryPreview")}</button>
          </div>
        ) : <p role="status">{label(t, "loadingPreview")}</p>}
      </div>
    </>
  );
}

function jumpToHeading(ref) {
  ref.current?.focus({ preventScroll: true });
  ref.current?.scrollIntoView({ block: "start" });
}

function ReviewField({ t, name, value, conflict, onChange }) {
  return (
    <div className="intake-field">
      <label>
        {errorLabel(t, `field_${name}`)}
        {name === "unlimited_validity" ? (
          <select value={typeof value === "boolean" ? String(value) : ""} onChange={event =>
            onChange(event.target.value === "" ? null : event.target.value === "true")
          }>
            <option value="">{label(t, "unset")}</option>
            <option value="true">{label(t, "yes")}</option>
            <option value="false">{label(t, "no")}</option>
          </select>
        ) : name === "remarks" ? (
          <textarea value={value ?? ""} onChange={event => onChange(event.target.value)} />
        ) : (
          <input type={isDate(name) ? "date" : "text"} value={value ?? ""} onChange={event => onChange(event.target.value)} />
        )}
      </label>
      {conflict && (
        <div className="intake-warning">
          {label(t, "conflict")}{" "}
          <button type="button" className="secondary-btn" onClick={() => onChange(null)}>{label(t, "leaveBlank")}</button>
        </div>
      )}
    </div>
  );
}

function RecordFields({ t, fields }) {
  return (
    <dl className="intake-record-fields">
      {Object.entries(fields).filter(([, value]) => value !== "" && value != null).map(([name, value]) => (
        <React.Fragment key={name}>
          <dt>{errorLabel(t, `field_${name}`)}</dt>
          <dd>{typeof value === "boolean" ? label(t, value ? "yes" : "no") : value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function ReviewEditor({ doc, spec, matches, typesByKind, candidateName, patch, t }) {
  const warnings = new Set(doc.files.flatMap(file => file.warnings ?? []).filter(code => code !== "ocr_used" && code !== "mrz_used"));
  if (hasHolderMismatch(doc)) warnings.add("holder_mismatch");
  if (hasTypeMismatch(doc)) warnings.add("type_hint_mismatch");
  const selectedRecord = matches.targets.find(record => String(record.id) === doc.existingId);
  const staleRecord = Boolean(doc.existingId && selectedRecord?.version !== doc.existingVersion);
  const chooseRecord = record => ({
    existingId: record ? String(record.id) : "", existingVersion: record?.version ?? "",
  });
  const changeField = (name, value) => patch({
    fields: { ...doc.fields, [name]: value },
    conflicts: doc.conflicts.filter(field => field !== name),
    ...(name === "number" ? { action: "", ...chooseRecord() } : {}),
    ...(name === "holder_name" ? { confirmHolder: false } : {}),
  });
  return (
    <>
      <label>
        {label(t, "type")}
        <select value={doc.typeKey} onChange={event => patch({
          typeKey: event.target.value, action: "", ...chooseRecord(), confirmHolder: false, confirmTypeMismatch: false,
        })}>
          <option value="">{label(t, "unknown")}</option>
          {Object.entries(typesByKind).map(([kind, types]) => (
            <optgroup key={kind} label={label(t, `kind_${kind}`)}>
              {types.map(type => <option key={type.key} value={type.key}>{t(type.label)}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
      {!spec && <p>{label(t, "chooseType")}</p>}
      {warnings.size > 0 && (
        <ul className="intake-warning">
          {[...new Set([...warnings].map(code => {
            const [kind, field] = code.split(":");
            const fieldName = Object.hasOwn(catalog, key(`field_${field}`)) ? label(t, `field_${field}`) : "";
            return label(t, fieldName && Object.hasOwn(catalog, key(`warning_${kind}`)) ? `warning_${kind}`
              : Object.hasOwn(catalog, key(code)) ? code : "uncertain", { field: fieldName });
          }))].map(message => <li key={message}>{message}</li>)}
        </ul>
      )}
      {spec && (
        <div className="intake-fields">
          {spec.fields.map(name => <ReviewField key={name} t={t} name={name} value={doc.fields[name]}
            conflict={doc.conflicts.includes(name)} onChange={value => changeField(name, value)} />)}
        </div>
      )}
      {matches.records.length > 0 && (
        <section className="intake-matches">
          <h4>{label(t, "matches")}</h4>
          <p>{label(t, matches.exact.length ? "exact" : "sameType")}</p>
          <label>
            {label(t, "chooseAction")}
            <select value={doc.action} onChange={event => patch({
              action: event.target.value,
              ...chooseRecord(event.target.value === "update" && matches.targets.length === 1 ? matches.targets[0] : null),
            })}>
              <option value="">{label(t, "selectAction")}</option>
              {matches.canCreate && <option value="create">{label(t, "create")}</option>}
              <option value="update">{label(t, "update")}</option>
              <option value="skip">{label(t, "skip")}</option>
            </select>
          </label>
          {doc.action === "update" && (
            <>
              <label>
                {label(t, "chooseRecord")}
                <select value={staleRecord ? "" : doc.existingId} onChange={event =>
                  patch(chooseRecord(matches.targets.find(record => String(record.id) === event.target.value)))}>
                  <option value="">{label(t, "selectRecord")}</option>
                  {matches.targets.map(record => (
                    <option key={record.id} value={record.id}>
                      {label(t, record.fields.number ? "recordLabel" : "noNumber", { number: record.fields.number, id: record.id })}
                    </option>
                  ))}
                </select>
              </label>
              {staleRecord && <p role="status">{t("intake.record_changed")}</p>}
              <p>{label(t, "preserve")}</p>
            </>
          )}
          {matches.records.map(record => (
            <details key={record.id} open={matches.records.length === 1 || String(record.id) === doc.existingId ? true : undefined}>
              <summary>
                {label(t, record.fields.number ? "recordLabel" : "noNumber", { number: record.fields.number, id: record.id })}
              </summary>
              <RecordFields t={t} fields={record.fields} />
            </details>
          ))}
        </section>
      )}
      {hasHolderMismatch(doc) && (
        <label className="intake-check">
          <input type="checkbox" checked={doc.confirmHolder} onChange={event => patch({ confirmHolder: event.target.checked })} />
          {label(t, "confirmHolder", { name: candidateName })}
        </label>
      )}
      {hasTypeMismatch(doc) && (
        <label className="intake-check">
          <input type="checkbox" checked={doc.confirmTypeMismatch}
            onChange={event => patch({ confirmTypeMismatch: event.target.checked })} />
          {label(t, "confirmTypeMismatch")}
        </label>
      )}
    </>
  );
}

export default function DocumentIntakeEntry({ candidateId, onSaved }) {
  const { user, token } = useAuth();
  const draftScope = reviewDraftKey(user, candidateId);
  const [draftSession, setDraftSession] = useState(() => reviewDraftSession(token));
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    async function check() {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        const next = await fetchIntakeStatus(candidateId, controller.signal);
        if (!controller.signal.aborted) setEnabled(next);
      } catch {
        // A transient network error must not discard a manager's open review.
      } finally {
        inFlight = false;
      }
    }
    void check();
    const timer = window.setInterval(check, 15000);
    window.addEventListener("focus", check);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, [candidateId]);
  useEffect(() => {
    function syncSession() {
      const stored = localStorage.getItem("authToken");
      const storedUser = JSON.parse(localStorage.getItem("authUser") || "null");
      const next = reviewDraftSession(stored);
      syncReviewDraftSession(next);
      setDraftSession(reviewDraftKey(storedUser, candidateId) === draftScope && storedUser?.role === user?.role ? next : "");
    }
    function onStorage(event) {
      if (event.key == null || event.key === "authToken" || event.key === "authUser") syncSession();
    }
    syncSession();
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [candidateId, draftScope, token, user?.role]);
  return enabled && draftSession ? <DocumentIntake key={JSON.stringify([draftSession, draftScope])}
    candidateId={candidateId} onSaved={onSaved} draftScope={draftScope} draftSession={draftSession} /> : null;
}

function DocumentIntake({ candidateId, onSaved, draftScope, draftSession }) {
  const dialog = useRef(null);
  const lifetime = useRef(null);
  const pendingCardKinds = useRef(new Set());
  const folderInput = useRef(null);
  const filesInput = useRef(null);
  const originalHeading = useRef(null);
  const fieldsHeading = useRef(null);
  const comparison = useRef(null);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [batches, setBatches] = useState([]);
  const [batchId, setBatchId] = useState("");
  const [activeId, setActiveId] = useState("");
  const [fileId, setFileId] = useState("");
  const [selection, setSelection] = useState(new Set());
  const [operation, setOperation] = useState("");
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [draftStorageAvailable, setDraftStorageAvailable] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    setDraftStorageAvailable(syncReviewDraftSession(draftSession) &&
      writeReviewDrafts(draftScope, batches, data?.batches.map(batch => batch.batch_id)
        .concat(batches.map(batch => batch.id))));
  }, [batches, data, draftScope, draftSession]);

  function applyRemote(next, clearUnconfirmed = false) {
    const drafts = readReviewDrafts(draftScope);
    setData(next);
    setBatches(previous => mergeRemoteBatches(previous, next.batches, drafts).map(batch =>
      clearUnconfirmed ? { ...batch, documents: batch.documents.map(doc =>
        doc.error === "save_outcome_unknown" ? { ...doc, error: "" } : doc) } : batch));
  }

  const batch = batches.find(item => item.id === batchId) ?? batches.at(-1);
  const processing = Boolean(batch && batch.processed < batch.total);
  const hasPending = batches.some(item => item.processed < item.total);
  const documents = batch?.documents ?? [];
  const active = documents.find(doc => doc.id === activeId) ?? documents.find(isReviewable) ?? documents[0];
  const file = active?.files.find(item => item.file_id === fileId) ?? active?.files[0];
  const types = new Map((data?.catalog ?? []).map(spec => [spec.key, spec]));
  const typesByKind = {};
  for (const spec of types.values()) (typesByKind[spec.kind] ??= []).push(spec);
  const matchesFor = doc => findMatches(doc, data?.existing ?? []);
  const approval = (doc, individual) => approvalFor(doc, types.get(doc.typeKey), matchesFor(doc), individual);
  const selected = documents.filter(doc => selection.has(doc.id) && isReviewable(doc));
  const bulk = selected.map(doc => approval(doc, false)).filter(Boolean);

  useEffect(() => {
    if (!open || !hasPending || operation) return;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const next = await fetchIntake(candidateId, controller.signal);
        if (!controller.signal.aborted) {
          applyRemote(next);
        }
      } catch {
        // Keep the last known progress and try again after a transient error.
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(poll, 2000);
      }
    }
    timer = window.setTimeout(poll, 2000);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [candidateId, draftScope, hasPending, open, operation]);

  function changeBatch(id) {
    setBatchId(id);
    setActiveId("");
    setFileId("");
    setSelection(new Set());
  }

  function changeDocuments(transform) {
    setBatches(prev => prev.map(item => item.id === batch.id ? { ...item, documents: transform(item.documents) } : item));
  }

  async function run(phase, fallback, work) {
    if (operation) return;
    const { signal } = lifetime.current;
    setOperation(phase);
    setError("");
    setNotice(null);
    try {
      await work(signal);
    } catch (err) {
      if (!signal.aborted) setError(requestCode(err, fallback));
    } finally {
      if (!signal.aborted) setOperation("");
    }
  }

  async function refreshSavedCard(signal) {
    const kinds = [...pendingCardKinds.current];
    if (!kinds.length || signal.aborted) return;
    await onSaved(kinds);
    if (!signal.aborted) kinds.forEach(kind => pendingCardKinds.current.delete(kind));
  }

  function refresh() {
    return run("loading", "loadFailed", async signal => {
      await refreshSavedCard(signal);
      if (signal.aborted) return;
      const next = await fetchIntake(candidateId, signal);
      if (signal.aborted) return;
      applyRemote(next, true);
    });
  }

  function openReview() {
    dialog.current.showModal();
    setOpen(true);
    void refresh();
  }

  function reviewSubmission(submission) {
    dialog.current.showModal();
    setOpen(true);
    changeBatch(submission.submission_id);
    if (submission.status === "in_review") {
      void refresh();
      return;
    }
    void run("startingRecognition", "startRecognitionFailed", async signal => {
      const next = await recognizeIntakeSubmission(candidateId, submission.submission_id, signal);
      if (signal.aborted) return;
      setBatches(previous => [
        ...previous.filter(item => item.id !== next.batch_id),
        ...mergeRemoteBatches(previous, [next]),
      ]);
      changeBatch(next.batch_id);
      const updated = await fetchIntake(candidateId, signal);
      if (signal.aborted) return;
      applyRemote(updated);
    });
  }

  function chooseFiles(event) {
    const files = Array.from(event.target.files);
    event.target.value = "";
    if (!files.length) return;
    if (files.length > MAX_FILES || files.reduce((sum, item) => sum + item.size, 0) > MAX_BATCH_BYTES) {
      setNotice(null);
      setError(files.length > MAX_FILES ? "batch_file_limit" : "batch_size_limit");
      return;
    }
    setPercent(0);
    void run("upload", "uploadFailed", async signal => {
      const next = await uploadIntake(candidateId, files, progress => {
        if (!signal.aborted) setPercent(Math.min(100, Math.floor(100 * progress.loaded / (progress.total || 1))));
      }, signal);
      if (signal.aborted) return;
      setBatches(previous => [
        ...previous.filter(item => item.id !== next.batch_id),
        ...mergeRemoteBatches(previous, [next]),
      ]);
      changeBatch(next.batch_id);
    });
  }

  function group() {
    const files = selected.flatMap(doc => doc.files);
    const merged = makeDocument(selected.map(doc => ({ file_id: doc.id, fields: doc.fields, type_key: doc.typeKey })));
    merged.files = files;
    merged.conflicts = [...new Set([...merged.conflicts, ...selected.flatMap(doc => doc.conflicts)])];
    changeDocuments(previous => previous.flatMap(doc => doc.id === merged.id ? [merged] : selection.has(doc.id) ? [] : [doc]));
    setSelection(new Set());
    setActiveId(merged.id);
    setFileId("");
  }

  function ungroup() {
    if (!window.confirm(label(t, "ungroupConfirm"))) return;
    changeDocuments(previous => previous.flatMap(doc => doc.id === active.id ? doc.files.map(item => makeDocument([item])) : [doc]));
    setSelection(new Set());
    setActiveId(file.file_id);
  }

  function moveFile(delta) {
    const files = [...active.files];
    const index = files.indexOf(file);
    const target = index + delta;
    if (target < 0 || target >= files.length) return;
    [files[index], files[target]] = [files[target], files[index]];
    changeDocuments(previous => previous.map(doc => doc.id === active.id ? { ...doc, files } : doc));
    setFileId(file.file_id);
  }

  function save(payload, bulk = false) {
    if (!payload.length) return;
    const finishSubmission = Boolean(batch.external && bulk);
    if (finishSubmission) {
      const approved = new Set(payload.flatMap(item => item.file_ids));
      const remaining = documents.filter(doc => !doc.saved)
        .flatMap(doc => doc.files).filter(file => !approved.has(file.file_id));
      if (remaining.length && !window.confirm(label(t, "confirmFinishSubmission", { count: remaining.length }))) return;
    }
    void run("saving", "saveUnconfirmed", async signal => {
      const { results, submission_finished } = await saveIntake(candidateId, batch.id, payload, bulk, signal, finishSubmission);
      if (signal.aborted) return;
      const byFile = new Map(results.map(result => [result.file_ids[0], result]));
      const saved = documents.filter(doc => byFile.get(doc.files[0].file_id)?.status === "saved");
      const savedIds = new Set(saved.map(doc => doc.id));
      changeDocuments(previous => previous.map(doc => {
        const outcome = byFile.get(doc.files[0].file_id);
        if (!outcome) return doc;
        return { ...doc, saved: outcome.status === "saved", error: outcome.error ?? "",
          confirmHolder: false, confirmTypeMismatch: false };
      }));
      setSelection(prev => new Set([...prev].filter(id => !savedIds.has(id))));
      const firstFailure = documents.find(doc => byFile.get(doc.files[0].file_id)?.status === "error");
      if (firstFailure) {
        setActiveId(firstFailure.id);
        setFileId("");
      }
      if (submission_finished) {
        setBatches(previous => previous.filter(item => item.id !== batch.id));
        setData(previous => previous && { ...previous, batches: previous.batches.filter(item => item.batch_id !== batch.id) });
        changeBatch("");
      }
      if (saved.length) {
        setNotice({ code: submission_finished ? "submissionSavedCount" : "savedCount", count: saved.length });
        saved.forEach(doc => {
          const kind = types.get(doc.typeKey)?.kind;
          if (kind) pendingCardKinds.current.add(kind);
        });
        try {
          await refreshSavedCard(signal);
          if (signal.aborted) return;
          const next = await fetchIntake(candidateId, signal);
          if (!signal.aborted) applyRemote(next);
        } catch {
          if (!signal.aborted) setError("loadFailed");
        }
      }
    });
  }

  function discard() {
    if (!window.confirm(label(t, "confirmDiscard"))) return;
    void run("discarding", "discardFailed", async signal => {
      await discardIntake(candidateId, batch.id, signal, batch.external);
      if (signal.aborted) return;
      setData(previous => previous && { ...previous, batches: previous.batches.filter(item => item.batch_id !== batch.id) });
      setBatches(previous => previous.flatMap(item => {
        if (item.id !== batch.id) return [item];
        if (item.external) return [];
        const saved = item.documents.filter(doc => doc.saved);
        const count = saved.reduce((sum, doc) => sum + doc.files.length, 0);
        return count ? [{ ...item, documents: saved, processed: count, total: count }] : [];
      }));
      changeBatch("");
      setNotice({ code: "draftDiscarded" });
    });
  }

  function retryRecognition() {
    void run("retrying", "retryFailed", async signal => {
      const next = await retryIntake(candidateId, batch.id, signal);
      if (!signal.aborted) {
        setBatches(previous => previous.map(item =>
          item.id === batch.id ? mergeRemoteBatches(previous, [next])[0] : item));
      }
    });
  }

  const single = active ? approval(active, true) : null;
  const busy = Boolean(operation);
  return (
    <div className="candidate-document-intake" lang="ru">
      <button type="button" className="secondary-btn" onClick={openReview}>{label(t, "open")}</button>
      <CandidateUploadControls candidateId={candidateId} onReview={reviewSubmission} reviewBusy={busy}
        label={(code, params) => label(t, code, params)} errorLabel={code => errorLabel(t, code)} />
      <dialog ref={dialog} className="intake-dialog" aria-labelledby="intake-title" onClose={() => setOpen(false)}>
        {open && (
          <div className="intake-body">
            <header className="intake-header">
              <div>
                <h2 id="intake-title">{label(t, "title")}</h2>
                {data?.candidate_name && <p>{data.candidate_name}</p>}
              </div>
              <button type="button" className="secondary-btn" autoFocus onClick={() => dialog.current.close()}>{label(t, "close")}</button>
            </header>
            <p>{label(t, "privacy")}</p>
            <p>{label(t, "draftLifetime")}</p>
            {!draftStorageAvailable && <p role="status">{label(t, "draftStorageUnavailable")}</p>}
            <fieldset disabled={busy} className="intake-controls">
              <div className="intake-actions">
                <input hidden type="file" multiple ref={folderInput} webkitdirectory="" aria-label={label(t, "folder")} onChange={chooseFiles} />
                <input hidden type="file" multiple ref={filesInput} accept=".pdf,.jpg,.jpeg,.png" aria-label={label(t, "files")} onChange={chooseFiles} />
                <button type="button" onClick={() => folderInput.current.click()} disabled={!data}>{label(t, "folder")}</button>
                <button type="button" className="secondary-btn" onClick={() => filesInput.current.click()} disabled={!data}>{label(t, "files")}</button>
                <button type="button" className="secondary-btn" onClick={refresh}>{label(t, "retry")}</button>
              </div>
              <p>{label(t, "limits")}</p>
              {batch && (
                <div className="intake-actions">
                  <label>
                    {label(t, "batch")}
                    <select value={batch.id} onChange={event => changeBatch(event.target.value)}>
                      {batches.map(item => <option key={item.id} value={item.id}>{label(t, "batchOption", {
                        name: item.name, count: item.total,
                      })}</option>)}
                    </select>
                  </label>
                  <button type="button" className="secondary-btn" disabled={!processing && documents.every(doc => doc.saved)} onClick={discard}>{label(t, "discard")}</button>
                </div>
              )}
            </fieldset>
            {busy && <p role="status">{label(t, operation === "upload" && percent >= 100 ? "queueing" : operation, { percent })}</p>}
            {error && <p role="alert" className="error">{errorLabel(t, error)}</p>}
            {notice && <p role="status">{label(t, notice.code, notice)}</p>}
            {!batch && !busy && data && <p>{label(t, "empty")}</p>}
            {processing && (
              <div className="intake-progress">
                <p role="status">{label(t, "progress", { done: batch.processed, total: batch.total })}</p>
                <progress aria-label={label(t, "progressLabel")} value={batch.processed} max={batch.total} />
                <p>{label(t, "backgroundHint")}</p>
              </div>
            )}
            {batch && !processing && (
              <fieldset disabled={busy} className="intake-controls">
                <h3>{label(t, "documents")}</h3>
                <div className="intake-actions">
                  <button type="button" className="secondary-btn" disabled={selected.length < 2} onClick={group}>{label(t, "group", { count: selected.length })}</button>
                  <button type="button" disabled={!bulk.length} onClick={() => save(bulk, true)}>{label(t, "saveSelected", { count: bulk.length })}</button>
                  {documents.some(doc => doc.files.some(item => item.retryable)) && (
                    <button type="button" className="secondary-btn" onClick={retryRecognition}>{label(t, "retryRecognition")}</button>
                  )}
                </div>
                {selected.length > bulk.length && <p>{label(t, batch.external ? "submissionExcluded" : "excluded", { count: selected.length - bulk.length })}</p>}
                <ul className="intake-documents">
                  {documents.map(doc => (
                    <li key={doc.id}>
                      <input type="checkbox" aria-label={label(t, "select", { name: doc.files[0].name })}
                        disabled={!isReviewable(doc)} checked={selection.has(doc.id)} onChange={event => {
                          const checked = event.target.checked;
                          setSelection(previous => {
                            const next = new Set(previous);
                            if (checked) next.add(doc.id);
                            else next.delete(doc.id);
                            return next;
                          });
                        }} />
                      <button type="button" className="secondary-btn" aria-current={active?.id === doc.id ? "true" : undefined}
                        onClick={() => {
                          setActiveId(doc.id);
                          setFileId("");
                          if (isReviewable(doc)) {
                            requestAnimationFrame(() => comparison.current?.scrollIntoView({ block: "start" }));
                          }
                        }}>
                        <strong>{doc.files[0].name}</strong>
                        <span>{doc.saved ? label(t, "saved") : !isReviewable(doc) ? label(t, "failed") : t(types.get(doc.typeKey)?.label || key("unknown"))}
                          {doc.files.length > 1 && ` · ${label(t, "grouped", { count: doc.files.length })}`}
                        </span>
                      </button>
                      {doc.error && <span className="intake-row-error">{errorLabel(t, doc.error)}</span>}
                    </li>
                  ))}
                </ul>
                {active && isReviewable(active) && (
                  <div ref={comparison} className="intake-review">
                    <section className="intake-original">
                      <div className="intake-pane-heading">
                        <h3 ref={originalHeading} tabIndex={-1}>{label(t, "original")}</h3>
                        <button type="button" className="secondary-btn intake-mobile-jump" onClick={() => jumpToHeading(fieldsHeading)}>
                          {label(t, "jumpToFields")}
                        </button>
                      </div>
                      {active.files.length > 1 && (
                        <>
                          <label>
                            {label(t, "originalFile")}
                            <select value={file.file_id} onChange={event => setFileId(event.target.value)}>
                              {active.files.map((item, index) => <option key={item.file_id} value={item.file_id}>{index + 1}. {item.name}</option>)}
                            </select>
                          </label>
                          <div className="intake-actions">
                            <button type="button" className="secondary-btn" disabled={active.files[0] === file} onClick={() => moveFile(-1)}>{label(t, "reorderUp")}</button>
                            <button type="button" className="secondary-btn" disabled={active.files.at(-1) === file} onClick={() => moveFile(1)}>{label(t, "reorderDown")}</button>
                            <button type="button" className="secondary-btn" onClick={ungroup}>{label(t, "ungroup")}</button>
                          </div>
                        </>
                      )}
                      <ScanPreview key={file.file_id} candidateId={candidateId} batchId={batch.id} file={file} t={t} />
                    </section>
                    <section className="intake-editor">
                      <div className="intake-pane-heading">
                        <h3 ref={fieldsHeading} tabIndex={-1}>{label(t, "fields")}</h3>
                        <button type="button" className="secondary-btn intake-mobile-jump" onClick={() => jumpToHeading(originalHeading)}>
                          {label(t, "jumpToOriginal")}
                        </button>
                      </div>
                      <ReviewEditor doc={active} spec={types.get(active.typeKey)} matches={matchesFor(active)} typesByKind={typesByKind}
                        candidateName={data?.candidate_name} t={t} patch={changes =>
                          changeDocuments(previous => previous.map(doc => doc.id === active.id ? { ...doc, ...changes } : doc))
                        } />
                      {active.error && <p role="alert" className="error">{errorLabel(t, active.error)}</p>}
                      <button type="button" disabled={!single} onClick={() => save([single])}>{label(t, "save")}</button>
                    </section>
                  </div>
                )}
              </fieldset>
            )}
          </div>
        )}
      </dialog>
    </div>
  );
}
