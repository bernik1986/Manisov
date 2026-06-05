/**
 * Short label for scan download links in tables (full name stays in title / download).
 * Convention: "RANK Surname SLOT.pdf" → "RANK..."
 */
export function formatScanDisplayLabel(fileName, maxRankLen = 20) {
  if (!fileName || typeof fileName !== "string") {
    return "Скан...";
  }
  const base = fileName.split(/[/\\]/).pop() || fileName;
  const stem = base.replace(/\.[^.]+$/, "");
  const rank = (stem.includes(" ") ? stem.split(" ")[0] : stem.split("_")[0])?.trim();
  if (!rank) {
    const fallback = stem.length > maxRankLen ? `${stem.slice(0, maxRankLen)}` : stem;
    return fallback ? `${fallback}...` : "Скан...";
  }
  const shown = rank.length > maxRankLen ? rank.slice(0, maxRankLen) : rank;
  return `${shown}...`;
}
