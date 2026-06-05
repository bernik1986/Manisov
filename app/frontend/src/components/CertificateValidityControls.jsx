import React from "react";
import {
  VALIDITY_MODE,
  applyPlus5Years,
  applyValidityMode,
} from "../utils/certificateValidity";

const MODE_OPTIONS = [
  { value: VALIDITY_MODE.PLUS5, label: "+5 лет" },
  { value: VALIDITY_MODE.UNLIMITED, label: "Unlimited" },
  { value: VALIDITY_MODE.OTHER, label: "Другое" },
];

export default function CertificateValidityControls({
  validityMode,
  onValidityModeChange,
  onDraftChange,
  draft,
  disabled = false,
}) {
  function setMode(mode) {
    onValidityModeChange(mode);
    onDraftChange({ ...applyValidityMode(draft, mode), validityMode: mode });
  }

  function handleApplyPlus5() {
    onValidityModeChange(VALIDITY_MODE.PLUS5);
    onDraftChange({ ...applyPlus5Years({ ...draft, unlimited_validity: false }), validityMode: VALIDITY_MODE.PLUS5 });
  }

  return (
    <div className="certificate-validity-controls">
      <span className="certificate-validity-label">Срок действия:</span>
      <div className="certificate-validity-modes" role="radiogroup" aria-label="Срок действия сертификата">
        {MODE_OPTIONS.map(({ value, label }) => (
          <label key={value} className="certificate-validity-option">
            <input
              type="radio"
              name="certificate-validity-mode"
              value={value}
              checked={validityMode === value}
              disabled={disabled}
              onChange={() => setMode(value)}
            />
            {label}
          </label>
        ))}
      </div>
      {validityMode === VALIDITY_MODE.OTHER ? (
        <button type="button" className="secondary-btn certificate-validity-apply-btn" disabled={disabled} onClick={handleApplyPlus5}>
          Применить +5 лет
        </button>
      ) : null}
    </div>
  );
}
