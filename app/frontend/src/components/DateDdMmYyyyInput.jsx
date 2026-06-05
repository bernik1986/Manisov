import React from "react";
import {
  dateFieldHasInvalidCalendar,
  dateFieldInlineErrorMessage,
  normalizeMaskedDateValue,
} from "../utils/dateInputSupport";

/**
 * Masked DD-MM-YYYY text field. Red border + message when 8 digits form an impossible date.
 * Optional `error` from parent (e.g. range validation) overrides inline calendar message.
 */
export default function DateDdMmYyyyInput({
  value,
  onChange,
  disabled,
  readOnly,
  className = "",
  id,
  placeholder = "дд-мм-гггг",
  error: externalError,
}) {
  const invalidCalendar = dateFieldHasInvalidCalendar(value);
  const inlineMsg = dateFieldInlineErrorMessage(value);
  const showError = Boolean(externalError) || invalidCalendar;
  const message = externalError || (invalidCalendar ? inlineMsg : "");

  function handleChange(event) {
    if (readOnly || disabled) {
      return;
    }
    const next = normalizeMaskedDateValue(event.target.value);
    onChange(next);
  }

  return (
    <span className="date-field-wrap">
      <input
        id={id}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        className={`${className} ${showError ? "input-date-invalid" : ""}`.trim()}
        value={value ?? ""}
        onChange={handleChange}
        disabled={disabled}
        readOnly={readOnly}
        aria-invalid={showError || undefined}
      />
      {showError && message ? <span className="field-error-text">{message}</span> : null}
    </span>
  );
}
