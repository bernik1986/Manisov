import dayjs from "dayjs";
import { toIsoDateString, toUiDateString } from "./dateInputSupport";

export const VALIDITY_MODE = {
  PLUS5: "plus5",
  UNLIMITED: "unlimited",
  OTHER: "other",
};

export const VALIDITY_YEARS = 5;

/** True when issue/expiry pair is incomplete (e.g. after CV parse). Not used to hide edit UI. */
export function needsValidityAssist(cert) {
  if (!cert) {
    return true;
  }
  if (cert.unlimited_validity === true) {
    return false;
  }
  const issued = toIsoDateString(cert.date_issued);
  const expiry = toIsoDateString(cert.expiry_date);
  return !(issued && expiry);
}

function addCalendarYearsUi(dateUi, years) {
  const iso = toIsoDateString(dateUi);
  if (!iso) {
    return "";
  }
  return toUiDateString(dayjs(iso).add(years, "year").format("YYYY-MM-DD"));
}

function subCalendarYearsUi(dateUi, years) {
  const iso = toIsoDateString(dateUi);
  if (!iso) {
    return "";
  }
  return toUiDateString(dayjs(iso).subtract(years, "year").format("YYYY-MM-DD"));
}

/** Compute missing date from the one that is set (+5 calendar years). */
export function applyPlus5Years(draft) {
  const out = { ...draft, unlimited_validity: false };
  const issuedIso = toIsoDateString(draft.date_issued);
  const expiryIso = toIsoDateString(draft.expiry_date);

  if (issuedIso && !expiryIso) {
    out.expiry_date = addCalendarYearsUi(draft.date_issued, VALIDITY_YEARS);
  } else if (expiryIso && !issuedIso) {
    out.date_issued = subCalendarYearsUi(draft.expiry_date, VALIDITY_YEARS);
  } else if (issuedIso && expiryIso) {
    out.expiry_date = addCalendarYearsUi(draft.date_issued, VALIDITY_YEARS);
  }
  return out;
}

export function applyValidityMode(draft, mode) {
  const resolved = mode || VALIDITY_MODE.PLUS5;
  if (resolved === VALIDITY_MODE.UNLIMITED) {
    return {
      ...draft,
      unlimited_validity: true,
      expiry_date: "",
    };
  }
  if (resolved === VALIDITY_MODE.PLUS5) {
    return applyPlus5Years({ ...draft, unlimited_validity: false });
  }
  return { ...draft, unlimited_validity: false };
}

export function inferValidityMode(cert) {
  if (cert?.unlimited_validity === true) {
    return VALIDITY_MODE.UNLIMITED;
  }
  const issuedIso = toIsoDateString(cert?.date_issued);
  const expiryIso = toIsoDateString(cert?.expiry_date);
  if (issuedIso && expiryIso) {
    const expected = dayjs(issuedIso).add(VALIDITY_YEARS, "year").format("YYYY-MM-DD");
    if (expected === expiryIso) {
      return VALIDITY_MODE.PLUS5;
    }
  }
  return VALIDITY_MODE.OTHER;
}

export function patchCertificateWithValidity(prevCertificate, patch, validityMode) {
  let next = { ...prevCertificate, ...patch };
  if (validityMode === VALIDITY_MODE.PLUS5) {
    next = applyPlus5Years(next);
  } else if (validityMode === VALIDITY_MODE.UNLIMITED) {
    next = { ...next, unlimited_validity: true, expiry_date: "" };
  }
  return next;
}

/** Prepare API payload after validity rules; strips UI-only validityMode. */
export function certificatePayloadFromDraft(draft) {
  const mode = draft.validityMode ?? inferValidityMode(draft);
  const applied = applyValidityMode(draft, mode);
  const { validityMode: _drop, ...rest } = applied;
  const payload = { ...rest };
  if (mode === VALIDITY_MODE.UNLIMITED) {
    payload.unlimited_validity = true;
    payload.expiry_date = null;
  } else {
    payload.unlimited_validity = false;
  }
  return payload;
}

export function formatCertificateExpiryDisplay(cert) {
  if (cert?.unlimited_validity === true) {
    return "Unlimited";
  }
  const expiry = cert?.expiry_date;
  if (expiry === null || expiry === undefined || expiry === "") {
    return "";
  }
  return toUiDateString(expiry) || String(expiry);
}

export function mergeCertificateDateChange(cert, field, value, validityMode) {
  const mode = validityMode ?? cert?.validityMode ?? VALIDITY_MODE.PLUS5;
  if (mode === VALIDITY_MODE.PLUS5 && field === "expiry_date") {
    return { ...cert, expiry_date: value, validityMode: VALIDITY_MODE.OTHER };
  }
  if (mode === VALIDITY_MODE.PLUS5) {
    return { ...patchCertificateWithValidity(cert, { [field]: value }, mode), validityMode: mode };
  }
  return { ...cert, [field]: value, validityMode: mode };
}
