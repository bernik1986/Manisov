import { useEffect, useState } from "react";
import { DOCUMENT_UPLOAD_INBOX_CHANGED, fetchIntakeNotifications, fetchIntakeSubmissions } from "../documentIntakeApi.js";

const empty = { items: [], enabled: false, uploadEnabled: false, failed: false };
const refreshInterval = 15000;

export default function useDocumentUploadInbox(active, candidateId) {
  const [snapshot, setSnapshot] = useState(empty);

  useEffect(() => {
    if (!active) {
      setSnapshot(empty);
      return undefined;
    }
    let request;
    let timer;

    async function refresh() {
      window.clearTimeout(timer);
      if (document.hidden) return;
      request?.abort();
      const controller = new AbortController();
      request = controller;
      try {
        const result = candidateId
          ? await fetchIntakeSubmissions(candidateId, controller.signal)
          : await fetchIntakeNotifications(controller.signal);
        if (controller.signal.aborted) return;
        setSnapshot({
          items: Array.isArray(result.items) ? result.items : [],
          enabled: result.enabled !== false,
          uploadEnabled: result.upload_enabled === true,
          failed: false,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        if ([403, 404].includes(error?.response?.status)) {
          setSnapshot(empty);
        } else {
          setSnapshot(previous => ({ ...previous, failed: true }));
        }
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(refresh, refreshInterval);
      }
    }

    void refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener(DOCUMENT_UPLOAD_INBOX_CHANGED, refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      request?.abort();
      window.clearTimeout(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener(DOCUMENT_UPLOAD_INBOX_CHANGED, refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [active, candidateId]);

  return snapshot;
}

export function formatSubmissionDate(value) {
  if (!value) return "";
  const utc = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`;
  const timestamp = new Date(utc);
  return Number.isNaN(timestamp.getTime()) ? "" : timestamp.toLocaleString("ru-RU", {
    dateStyle: "short", timeStyle: "short",
  });
}
