export function getExpirationStatus(expiryDate) {
  if (!expiryDate) return "normal";

  const exp = new Date(expiryDate);
  if (Number.isNaN(exp.getTime())) return "normal";

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(exp.getFullYear(), exp.getMonth(), exp.getDate());
  const msInDay = 24 * 60 * 60 * 1000;
  const daysLeft = Math.floor((target - today) / msInDay);

  if (daysLeft < 0) return "expired";
  if (daysLeft < 240) return "warning";
  return "normal";
}
