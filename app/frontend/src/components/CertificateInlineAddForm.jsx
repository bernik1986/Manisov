import React from "react";
import DateDdMmYyyyInput from "./DateDdMmYyyyInput";
import CertificateValidityControls from "./CertificateValidityControls";
import { VALIDITY_MODE } from "../utils/certificateValidity";

const emptyDraft = {
  certificate_type: "",
  certificate_number: "",
  issuing_authority: "",
  date_issued: "",
  expiry_date: "",
  validityMode: VALIDITY_MODE.PLUS5,
  unlimited_validity: false,
};

export function createEmptyCertificateDraft() {
  return { ...emptyDraft };
}

export default function CertificateInlineAddForm({ draft, onDraftChange, onAdd, disabled = false }) {
  const validityMode = draft.validityMode ?? VALIDITY_MODE.PLUS5;

  return (
    <div className="inline-form certificate-inline-form">
      <input
        type="text"
        placeholder="Тип сертификата"
        value={draft.certificate_type || ""}
        disabled={disabled}
        onChange={(event) => onDraftChange({ ...draft, certificate_type: event.target.value })}
      />
      <input
        type="text"
        placeholder="Номер"
        value={draft.certificate_number || ""}
        disabled={disabled}
        onChange={(event) => onDraftChange({ ...draft, certificate_number: event.target.value })}
      />
      <input
        type="text"
        placeholder="Кем выдан"
        value={draft.issuing_authority || ""}
        disabled={disabled}
        onChange={(event) => onDraftChange({ ...draft, issuing_authority: event.target.value })}
      />
      <DateDdMmYyyyInput
        value={draft.date_issued || ""}
        disabled={disabled}
        onChange={(next) => onDraftChange({ ...draft, date_issued: next })}
      />
      <DateDdMmYyyyInput
        value={draft.expiry_date || ""}
        disabled={disabled}
        onChange={(next) => onDraftChange({ ...draft, expiry_date: next })}
      />
      <button type="button" onClick={onAdd} disabled={disabled}>
        Добавить
      </button>
      <div className="certificate-inline-form__validity">
        <CertificateValidityControls
          validityMode={validityMode}
          draft={draft}
          disabled={disabled}
          onValidityModeChange={(mode) => onDraftChange({ ...draft, validityMode: mode })}
          onDraftChange={onDraftChange}
        />
      </div>
    </div>
  );
}
