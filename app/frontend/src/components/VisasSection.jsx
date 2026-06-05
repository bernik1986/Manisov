import React from "react";
import DateDdMmYyyyInput from "./DateDdMmYyyyInput";
import FileDropzone from "./FileDropzone";
import ScanDownloadLink from "./ScanDownloadLink";
import {
  CANONICAL_VISA_SPECS,
  canonicalVisaPlaceholderLines,
  findCanonicalVisaSpecForRow,
  isCanonicalVisaRow,
  isCustomVisaRow,
  visaRowCode,
} from "../canonicalVisas";
import dayjs from "dayjs";

function getId(item, fallbackKeys = []) {
  if (item == null) return null;
  for (const key of ["id", ...fallbackKeys]) {
    const value = item[key];
    if (value != null && value !== "") return value;
  }
  return null;
}

function getExpiryClass(expiryDate) {
  if (!expiryDate) return "";
  const expiry = dayjs(expiryDate, ["DD-MM-YYYY", "YYYY-MM-DD"], true);
  if (!expiry.isValid()) return "";
  const days = expiry.diff(dayjs(), "day");
  if (days < 0) return "expired-row";
  if (days <= 90) return "expiring-row";
  return "";
}

const VISA_EDIT_FIELDS = ["document_number", "date_of_issue", "date_of_expiry"];

function visaRowFilled(item) {
  return Boolean(
    String(item.document_number || "").trim() &&
      String(item.date_of_issue || "").trim() &&
      String(item.date_of_expiry || "").trim()
  );
}

export function validateVisaSavePayload(payload, row) {
  const number = String(payload.document_number ?? row?.document_number ?? "").trim();
  const issue = String(payload.date_of_issue ?? row?.date_of_issue ?? "").trim();
  const expiry = String(payload.date_of_expiry ?? row?.date_of_expiry ?? "").trim();
  if (!number) return "Укажите номер визы";
  if (!issue) return "Укажите дату выдачи";
  if (!expiry) return "Укажите дату окончания";
  return null;
}

export default function VisasSection({
  displayVisas,
  canEditRelations,
  focusTarget,
  editingVisaId,
  editDraft,
  onEditDraftChange,
  newVisaDraft,
  onNewVisaDraftChange,
  onBeginEdit,
  onCancelEdit,
  onSave,
  onAdd,
  onDelete,
  getRelationAttachment,
  onUploadRelationAttachment,
  onDeleteRelationAttachment,
  attachmentBusy,
  attachmentErrors,
}) {
  return (
    <>
      {canEditRelations ? (
        <div className="inline-form visas-add-form">
          <select
            value={newVisaDraft.mode}
            onChange={(event) =>
              onNewVisaDraftChange({
                ...newVisaDraft,
                mode: event.target.value,
                customName: event.target.value === "custom" ? newVisaDraft.customName : "",
              })
            }
            aria-label="Тип новой визы"
          >
            <option value="">— выберите визу —</option>
            {CANONICAL_VISA_SPECS.map((spec) => (
              <option key={spec.code} value={spec.code}>
                {spec.code}
              </option>
            ))}
            <option value="custom">Другая виза…</option>
          </select>
          {newVisaDraft.mode === "custom" ? (
            <input
              type="text"
              placeholder="Название / код визы"
              value={newVisaDraft.customName}
              onChange={(event) => onNewVisaDraftChange({ ...newVisaDraft, customName: event.target.value })}
              aria-label="Название новой визы"
            />
          ) : null}
          <input
            type="text"
            placeholder="Номер *"
            value={newVisaDraft.document_number}
            onChange={(event) =>
              onNewVisaDraftChange({ ...newVisaDraft, document_number: event.target.value })
            }
          />
          <DateDdMmYyyyInput
            value={newVisaDraft.date_of_issue}
            onChange={(next) => onNewVisaDraftChange({ ...newVisaDraft, date_of_issue: next })}
          />
          <DateDdMmYyyyInput
            value={newVisaDraft.date_of_expiry}
            onChange={(next) => onNewVisaDraftChange({ ...newVisaDraft, date_of_expiry: next })}
          />
          <button type="button" onClick={onAdd}>
            Добавить визу
          </button>
        </div>
      ) : (
        <p className="muted-text">Добавление и редактирование — для ролей admin и recruiter.</p>
      )}

      <details className="ukr-placeholders-details" style={{ marginBottom: "0.75rem" }}>
        <summary>Плейсхолдеры виз для Word (docxtpl)</summary>
        <pre className="ukr-placeholders-pre">{canonicalVisaPlaceholderLines().join("\n")}</pre>
      </details>

      <div className="table-wrap">
        <table className="candidate-table" data-testid="visas-table">
          <thead>
            <tr>
              <th>Виза</th>
              <th>Номер *</th>
              <th>Дата выдачи *</th>
              <th>Дата окончания *</th>
              <th className="scan-col">Скриншот</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {displayVisas.map((item) => {
              const relationId = getId(item, ["document_id"]);
              const rowId = relationId ?? `visa-placeholder-${visaRowCode(item)}`;
              const canonicalRow = isCanonicalVisaRow(item);
              const customRow = isCustomVisaRow(item);
              const isEditing = relationId != null && editingVisaId === relationId;
              const draft = isEditing ? editDraft : item;
              const label =
                findCanonicalVisaSpecForRow(item)?.documentType ||
                item.visa_code ||
                draft.document_type ||
                draft.document_category ||
                "—";
              const attachmentKey = `document:${relationId}`;
              const currentAttachment = getRelationAttachment("document", relationId);
              const busy = Boolean(attachmentBusy[attachmentKey]);
              const rowClass = getExpiryClass(item.date_of_expiry);
              const filled = visaRowFilled(item);

              return (
                <tr
                  key={rowId}
                  data-scan-target={`document:${relationId}`}
                  data-testid={label ? `visa-row-${label}` : undefined}
                  className={`${rowClass} ${focusTarget === `document:${relationId}` ? "scan-target-highlight" : ""}`.trim()}
                >
                  <td>{label}</td>
                  <td>
                    <input
                      type="text"
                      required
                      value={draft.document_number || ""}
                      disabled={!isEditing}
                      onChange={(event) => onEditDraftChange({ document_number: event.target.value })}
                    />
                  </td>
                  <td>
                    <DateDdMmYyyyInput
                      value={draft.date_of_issue || ""}
                      disabled={!isEditing}
                      onChange={(next) => onEditDraftChange({ date_of_issue: next })}
                    />
                  </td>
                  <td>
                    <DateDdMmYyyyInput
                      value={draft.date_of_expiry || ""}
                      disabled={!isEditing}
                      onChange={(next) => onEditDraftChange({ date_of_expiry: next })}
                    />
                  </td>
                  <td className={`scan-col ${!currentAttachment?.attachment_id ? "missing-scan-cell" : ""}`}>
                    <div className="scan-cell-inner">
                      <div className="scan-cell-toolbar">
                        {currentAttachment?.attachment_id ? (
                          <ScanDownloadLink
                            attachmentId={currentAttachment.attachment_id}
                            fileName={currentAttachment.file_name}
                          />
                        ) : (
                          <span className="muted-text">Нет скрина</span>
                        )}
                        {canEditRelations ? (
                          <FileDropzone
                            compact
                            disabled={busy || !relationId}
                            testId={`dropzone-visa-${relationId || rowId}`}
                            label={busy ? "Загрузка..." : currentAttachment ? "Заменить" : "Загрузить"}
                            onFile={(file) =>
                              relationId
                                ? onUploadRelationAttachment("document", relationId, file, currentAttachment)
                                : undefined
                            }
                          />
                        ) : null}
                        {canEditRelations && currentAttachment?.attachment_id ? (
                          <button
                            type="button"
                            className="danger-btn scan-delete-btn"
                            disabled={busy}
                            onClick={() =>
                              onDeleteRelationAttachment("document", relationId, currentAttachment.attachment_id)
                            }
                          >
                            Удалить
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {attachmentErrors[attachmentKey] ? (
                      <div className="error">{attachmentErrors[attachmentKey]}</div>
                    ) : null}
                  </td>
                  <td className="row-actions-cell">
                    <div className="actions-row">
                      {!canEditRelations ? (
                        <span className="muted-text">—</span>
                      ) : isEditing ? (
                        <>
                          <button type="button" onClick={() => onSave(relationId)}>
                            Сохранить
                          </button>
                          <button type="button" className="secondary-btn" onClick={onCancelEdit}>
                            Отмена
                          </button>
                        </>
                      ) : (
                        <>
                          <button type="button" onClick={() => onBeginEdit(item)}>
                            Редактировать
                          </button>
                          {customRow ? (
                            <button type="button" className="danger-btn" onClick={() => onDelete(relationId)}>
                              Удалить
                            </button>
                          ) : null}
                          {!filled && canonicalRow ? (
                            <span className="muted-text" style={{ marginLeft: 6 }}>
                              не заполнено
                            </span>
                          ) : null}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export { VISA_EDIT_FIELDS };
