import React, { useState } from "react";
import { downloadAttachment } from "../api";
import { formatScanDisplayLabel } from "../utils/scanDisplayLabel";

export default function ScanDownloadLink({ attachmentId, fileName, className = "attachment-link" }) {
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const label = formatScanDisplayLabel(fileName);

  async function openPreview(event) {
    event.preventDefault();
    if (!attachmentId || opening) return;
    setOpening(true);
    setError("");
    try {
      const { blob } = await downloadAttachment(attachmentId);
      const url = URL.createObjectURL(blob);
      const previewWindow = window.open(url, "_blank", "noopener,noreferrer");
      if (!previewWindow) {
        URL.revokeObjectURL(url);
        setError("Разрешите всплывающие окна для просмотра скана");
        return;
      }
      setTimeout(() => URL.revokeObjectURL(url), 120_000);
    } catch {
      setError("Не удалось открыть скан");
    } finally {
      setOpening(false);
    }
  }

  return (
    <span className="scan-download-link-wrap">
      <a
        href="#"
        className={`${className} scan-link-short`.trim()}
        title={fileName || undefined}
        data-testid="scan-download-link"
        aria-busy={opening}
        onClick={openPreview}
      >
        {opening ? "Открытие…" : label}
      </a>
      {error ? <span className="scan-download-link-error">{error}</span> : null}
    </span>
  );
}
