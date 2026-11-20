import React, { useCallback, useEffect, useRef, useState } from "react";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { dismissCommentReminder, fetchDueCommentReminders } from "../api";

const POLL_INTERVAL_MS = 30_000;

export default function CommentReminderAlerts() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [closingIds, setClosingIds] = useState(new Set());
  const [errorIds, setErrorIds] = useState(new Set());
  const lifetime = useRef(null);
  const pollRequest = useRef(0);

  const loadReminders = useCallback(async () => {
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted) return;
    const request = ++pollRequest.current;
    try {
      const payload = await fetchDueCommentReminders();
      if (signal.aborted || request !== pollRequest.current) return;
      setItems(Array.isArray(payload?.items) ? payload.items : []);
    } catch {
      // Keep already visible reminders on transient network errors.
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    loadReminders();
    const intervalId = window.setInterval(loadReminders, POLL_INTERVAL_MS);
    const onFocus = () => loadReminders();
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") loadReminders();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      controller.abort();
      pollRequest.current += 1;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [loadReminders]);

  async function closeReminder(commentId) {
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted) return;
    setClosingIds((current) => new Set(current).add(commentId));
    setErrorIds((current) => {
      const next = new Set(current);
      next.delete(commentId);
      return next;
    });
    try {
      await dismissCommentReminder(commentId);
      if (signal.aborted) return;
      // A poll started before this acknowledgement still contains the old reminder.
      pollRequest.current += 1;
      setItems((current) => current.filter((item) => item.comment_id !== commentId));
    } catch {
      if (!signal.aborted) setErrorIds((current) => new Set(current).add(commentId));
    } finally {
      if (!signal.aborted) {
        setClosingIds((current) => {
          const next = new Set(current);
          next.delete(commentId);
          return next;
        });
      }
    }
  }

  if (items.length === 0) return null;

  return (
    <aside className="comment-reminder-alerts" aria-label="Напоминания по морякам" data-testid="comment-reminder-alerts">
      {items.map((item) => (
        <article className="comment-reminder-alert" key={item.comment_id} data-testid="comment-reminder-alert">
          <button
            type="button"
            className="comment-reminder-close"
            aria-label="Закрыть напоминание"
            title="Закрыть напоминание"
            disabled={closingIds.has(item.comment_id)}
            onClick={() => closeReminder(item.comment_id)}
          >
            ×
          </button>
          <span className="comment-reminder-label">Напоминание</span>
          <strong>{item.candidate_name || `Моряк #${item.candidate_id}`}</strong>
          <p>{item.comment_text}</p>
          <time dateTime={item.reminder_at || ""}>
            {dayjs(item.reminder_at).isValid() ? dayjs(item.reminder_at).format("DD.MM.YYYY HH:mm") : ""}
          </time>
          <button
            type="button"
            className="comment-reminder-open"
            onClick={() => navigate(`/candidates/${item.candidate_id}?focus=comments`)}
          >
            Открыть карточку
          </button>
          {errorIds.has(item.comment_id) ? <small>Не удалось закрыть. Попробуйте ещё раз.</small> : null}
        </article>
      ))}
    </aside>
  );
}
