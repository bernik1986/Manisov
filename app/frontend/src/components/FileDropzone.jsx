import React, { useMemo, useRef, useState } from "react";

export default function FileDropzone({
  onFile,
  disabled = false,
  label = "Перетащите файл сюда или выберите",
  accept,
  inputId,
  testId,
  compact = false,
  browseLabel,
}) {
  const inputRef = useRef(null);
  const [isOver, setIsOver] = useState(false);

  const effectiveId = useMemo(() => inputId || `dropzone-${Math.random().toString(16).slice(2)}`, [inputId]);

  function pickFirstFile(files) {
    if (!files || !files.length) return null;
    return files[0] || null;
  }

  async function handleFile(file) {
    if (!file) return;
    await onFile?.(file);
  }

  const browseText = browseLabel || (compact ? "Файл" : "Browse");

  return (
    <div
      className={`file-dropzone ${compact ? "file-dropzone--compact" : ""} ${disabled ? "file-dropzone--disabled" : ""} ${isOver ? "file-dropzone--over" : ""}`}
      data-testid={testId}
      onDragEnter={(e) => {
        e.preventDefault();
        if (disabled) return;
        setIsOver(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (disabled) return;
        setIsOver(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setIsOver(false);
      }}
      onDrop={async (e) => {
        e.preventDefault();
        if (disabled) return;
        setIsOver(false);
        const file = pickFirstFile(e.dataTransfer?.files);
        await handleFile(file);
      }}
      role="group"
      aria-disabled={disabled ? "true" : "false"}
    >
      <div className="file-dropzone__row">
        {compact ? null : <span className="file-dropzone__label">{label}</span>}
        <button
          type="button"
          className="secondary-btn"
          disabled={disabled}
          title={label}
          onClick={() => inputRef.current?.click()}
        >
          {browseText}
        </button>
      </div>
      <input
        id={effectiveId}
        ref={inputRef}
        type="file"
        className="hidden-file-input"
        accept={accept}
        disabled={disabled}
        onChange={async (event) => {
          const file = pickFirstFile(event.target.files);
          await handleFile(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}

