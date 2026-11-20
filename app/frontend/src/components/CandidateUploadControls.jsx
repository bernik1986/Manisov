import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { discardIntakeSubmission, getOrCreateUploadLink, revokeUploadLink } from "../documentIntakeApi.js";
import useDocumentUploadInbox, { formatSubmissionDate } from "../utils/useDocumentUploadInbox.js";

export default function CandidateUploadControls({ candidateId, reviewBusy, onReview, label, errorLabel }) {
  const [searchParams] = useSearchParams();
  const focusId = searchParams.get("documentSubmission");
  const { items, uploadEnabled, failed } = useDocumentUploadInbox(true, candidateId);
  const focusedItem = useRef(null);
  const lastFocus = useRef("");
  const controller = useRef(null);
  const linkField = useRef(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const next = new AbortController();
    controller.current = next;
    return () => next.abort();
  }, []);

  const focused = items.some(item => item.submission_id === focusId);
  useEffect(() => {
    if (!focusId) lastFocus.current = "";
    if (focused && lastFocus.current !== focusId) {
      focusedItem.current?.focus();
      lastFocus.current = focusId;
    }
  }, [focused, focusId]);

  useEffect(() => {
    if (message === "uploadLinkManualCopy") {
      linkField.current?.focus();
      linkField.current?.select();
    }
  }, [message]);

  async function run(fallback, action) {
    if (busy) return;
    const { signal } = controller.current;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action(signal);
    } catch (failure) {
      if (!signal.aborted) setError(failure?.response?.data?.detail || fallback);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  function copyLink() {
    void run("uploadLinkFailed", async signal => {
      const token = await getOrCreateUploadLink(candidateId, signal);
      if (signal.aborted) return;
      if (typeof token !== "string" || !token) throw new Error("Missing upload token");
      const link = new URL("/upload-documents", window.location.origin);
      link.hash = token;
      const nextUrl = link.href;
      setUrl(nextUrl);
      try {
        await navigator.clipboard.writeText(nextUrl);
        if (!signal.aborted) setMessage("uploadLinkCopied");
      } catch {
        if (!signal.aborted) setMessage("uploadLinkManualCopy");
      }
    });
  }

  function revokeLink() {
    if (!window.confirm(label("uploadLinkConfirmRevoke"))) return;
    void run("uploadLinkRevokeFailed", async signal => {
      await revokeUploadLink(candidateId, signal);
      if (signal.aborted) return;
      setUrl("");
      setMessage("uploadLinkRevoked");
    });
  }

  function discard(item) {
    if (!window.confirm(label("submissionConfirmDiscard"))) return;
    void run("submissionDiscardFailed", async signal => {
      await discardIntakeSubmission(candidateId, item.submission_id, signal);
      if (!signal.aborted) setMessage("submissionDiscarded");
    });
  }

  return (
    <>
      {uploadEnabled && (
        <button type="button" className="secondary-btn" onClick={copyLink} disabled={busy}>
          {label("uploadLinkCopy")}
        </button>
      )}
      {(url || message || error) && (
        <div className="intake-link-panel">
          {url && <div className="intake-link-field">
            {uploadEnabled && <input ref={linkField} aria-label={label("uploadLink")} value={url} readOnly onFocus={event => event.currentTarget.select()} />}
            <button type="button" className="secondary-btn" onClick={revokeLink} disabled={busy}>{label("uploadLinkRevoke")}</button>
          </div>}
          {message && (uploadEnabled || !message.startsWith("uploadLink") || message === "uploadLinkRevoked") && (
            <p role="status">{label(message)}</p>
          )}
          {error && <p className="error" role="alert">{errorLabel(typeof error === "string" ? error : "requestFailed")}</p>}
        </div>
      )}
      {(items.length > 0 || failed) && (
        <section className="intake-inbox" aria-label={label("submissionsTitle")} data-testid="candidate-document-inbox">
          <h3>{label("submissionsTitle")}</h3>
          {failed && <p role="status">{label("submissionsLoadFailed")}</p>}
          <ul>
            {items.map(item => {
              const received = item.status === "received";
              const canReview = item.can_review !== false;
              const active = focusId === item.submission_id;
              const date = formatSubmissionDate(item.created_at);
              return (
                <li key={item.submission_id} ref={active ? focusedItem : null} tabIndex={active ? -1 : undefined}>
                  <div>
                    <strong>{label(received ? "submissionReceived" : "submissionInReview")}</strong>
                    <div className="muted-text">
                      {label("submissionFileCount", { count: item.file_count })}
                      {date && ` · ${date}`}
                    </div>
                  </div>
                  {canReview ? <div className="intake-actions">
                    <button type="button" onClick={() => onReview(item)} disabled={busy || reviewBusy}>
                      {label(received ? "submissionRecognize" : "submissionContinue")}
                    </button>
                    {received && <button type="button" className="secondary-btn" onClick={() => discard(item)} disabled={busy || reviewBusy}>
                      {label("submissionDiscard")}
                    </button>}
                  </div> : <span className="muted-text">{label("submissionAnotherReviewer")}</span>}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </>
  );
}
