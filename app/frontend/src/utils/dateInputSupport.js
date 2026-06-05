/** DD-MM-YYYY text dates for candidate UI (mask + validation). */

export const DATE_INVALID_MESSAGE = "Некорректная дата. Формат: ДД-ММ-ГГГГ.";
export const DATE_INCOMPLETE_MESSAGE = "Введите дату полностью: ДД-ММ-ГГГГ.";

export function formatDigitsAsDdMmYyyy(digitsRaw) {
  const d = String(digitsRaw).replace(/\D/g, "").slice(0, 8);
  if (d.length === 0) return "";
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)}-${d.slice(2)}`;
  return `${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4)}`;
}

/** Normalize pasted or typed value to masked DD-MM-YYYY partial string. */
export function normalizeMaskedDateValue(displayOrMixed) {
  return formatDigitsAsDdMmYyyy(displayOrMixed);
}

function calendarIsoStrict(dd, mm, yyyy) {
  if (mm < 1 || mm > 12 || dd < 1 || dd > 31) {
    return { ok: false, iso: null };
  }
  const dt = new Date(Date.UTC(yyyy, mm - 1, dd));
  if (dt.getUTCFullYear() !== yyyy || dt.getUTCMonth() !== mm - 1 || dt.getUTCDate() !== dd) {
    return { ok: false, iso: null };
  }
  const iso = `${String(yyyy).padStart(4, "0")}-${String(mm).padStart(2, "0")}-${String(dd).padStart(2, "0")}`;
  return { ok: true, iso };
}

/**
 * Parse UI or API date string to ISO yyyy-mm-dd or null.
 * Validates calendar for both ISO and DD-MM-YYYY (and ./. separators).
 */
export function toIsoDateString(value) {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const yyyy = value.getFullYear();
    const mm = String(value.getMonth() + 1).padStart(2, "0");
    const dd = String(value.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  const text = String(value).trim();
  const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoMatch) {
    const yyyy = parseInt(isoMatch[1], 10);
    const mm = parseInt(isoMatch[2], 10);
    const dd = parseInt(isoMatch[3], 10);
    const cal = calendarIsoStrict(dd, mm, yyyy);
    return cal.ok ? cal.iso : null;
  }

  const dmyMatch = text.match(/^(\d{2})[./-](\d{2})[./-](\d{4})$/);
  if (dmyMatch) {
    const dd = parseInt(dmyMatch[1], 10);
    const mm = parseInt(dmyMatch[2], 10);
    const yyyy = parseInt(dmyMatch[3], 10);
    const cal = calendarIsoStrict(dd, mm, yyyy);
    return cal.ok ? cal.iso : null;
  }

  return null;
}

export function toUiDateString(value) {
  const iso = toIsoDateString(value);
  if (!iso) return value;
  const [yyyy, mm, dd] = iso.split("-");
  return `${dd}-${mm}-${yyyy}`;
}

/** Full 8 digits entered but calendar invalid — show inline error. */
export function dateFieldHasInvalidCalendar(value) {
  const v = String(value ?? "").trim();
  if (!v) return false;
  const digits = v.replace(/\D/g, "");
  if (digits.length < 8) return false;
  return !validateUiDateStringForSubmit(v).ok;
}

export function dateFieldInlineErrorMessage(value) {
  const v = String(value ?? "").trim();
  if (!v) return "";
  const digits = v.replace(/\D/g, "");
  if (digits.length < 8) return "";
  const r = validateUiDateStringForSubmit(v);
  return r.ok ? "" : r.message || DATE_INVALID_MESSAGE;
}

/** For submit: empty ok; any non-empty must be complete and calendar-valid. */
export function validateUiDateStringForSubmit(value) {
  const v = String(value ?? "").trim();
  if (!v) return { ok: true, message: null };
  const digits = v.replace(/\D/g, "");
  if (digits.length < 8) {
    return { ok: false, message: DATE_INCOMPLETE_MESSAGE };
  }
  const norm = formatDigitsAsDdMmYyyy(digits.slice(0, 8));
  const m = norm.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (!m) {
    return { ok: false, message: DATE_INVALID_MESSAGE };
  }
  const cal = calendarIsoStrict(parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10));
  if (!cal.ok) {
    return { ok: false, message: DATE_INVALID_MESSAGE };
  }
  return { ok: true, message: null };
}
