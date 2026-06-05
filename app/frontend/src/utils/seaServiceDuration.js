import { toIsoDateString } from "./dateInputSupport";

/** Default Reason of Discharge for new sea service rows. */
export const SEA_SERVICE_DEFAULT_REMARKS = "EOC";

function isoToUtcDate(iso) {
  const [y, m, d] = iso.split("-").map((part) => parseInt(part, 10));
  return new Date(Date.UTC(y, m - 1, d));
}

/**
 * Contract length as Y/M/D (both sign-on and sign-off days inclusive).
 * Example: 23-12-2025 .. 03-05-2026 → "0/4/11"
 */
export function contractDurationYmd(signOn, signOff) {
  const onIso = toIsoDateString(signOn);
  const offIso = toIsoDateString(signOff);
  if (!onIso || !offIso) {
    return null;
  }

  const start = isoToUtcDate(onIso);
  const end = isoToUtcDate(offIso);
  if (end < start) {
    return null;
  }

  const endExclusive = new Date(end);
  endExclusive.setUTCDate(endExclusive.getUTCDate() + 1);

  let years = endExclusive.getUTCFullYear() - start.getUTCFullYear();
  let months = endExclusive.getUTCMonth() - start.getUTCMonth();
  let days = endExclusive.getUTCDate() - start.getUTCDate();

  if (days < 0) {
    months -= 1;
    const prevMonthEnd = new Date(Date.UTC(endExclusive.getUTCFullYear(), endExclusive.getUTCMonth(), 0));
    days += prevMonthEnd.getUTCDate();
  }
  if (months < 0) {
    years -= 1;
    months += 12;
  }

  return `${years}/${months}/${days}`;
}

export function withComputedContractDuration(seaServiceRow) {
  if (!seaServiceRow || typeof seaServiceRow !== "object") {
    return seaServiceRow;
  }
  const computed = contractDurationYmd(seaServiceRow.sign_on_date, seaServiceRow.sign_off_date);
  if (!computed) {
    return seaServiceRow;
  }
  return { ...seaServiceRow, contract_duration: computed };
}
