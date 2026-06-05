import React from "react";
import CertificateValidityControls from "./CertificateValidityControls";
import DateDdMmYyyyInput from "./DateDdMmYyyyInput";
import FileDropzone from "./FileDropzone";
import ScanDownloadLink from "./ScanDownloadLink";
import {
  VALIDITY_MODE,
  formatCertificateExpiryDisplay,
  inferValidityMode,
  mergeCertificateDateChange,
} from "../utils/certificateValidity";
import { certificateRowCode, certificateRowType } from "../canonicalCertificates";
import { diplomaRowCode, diplomaRowType, isWorkingCocDiplomaRow } from "../canonicalDiplomas";
import { medicalRowCode, medicalRowType } from "../canonicalMedical";

function getId(item, keys) {
  for (const key of keys) {
    if (item?.[key] != null) return item[key];
  }
  return null;
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  return String(value);
}

export default function CertificateRowsTable({
  items,
  section,
  canEditRelations,
  focusTarget,
  editingRowId,
  editDraft,
  setEditDrafts,
  attachmentBusy,
  attachmentErrors,
  getRelationAttachment,
  onUploadRelationAttachment,
  onDeleteRelationAttachment,
  onBeginEdit,
  onUpdate,
  onCancelEdit,
  onDelete,
  canDeleteRow,
  lockCanonicalType = false,
  showCodeColumn = false,
  showCocRankColumn = false,
  rowLabelMode = "certificate",
  diplomaSpecs = null,
  getRowExpiryClass,
}) {
  return (
    <div className="table-wrap">
      <table className="candidate-table">
        <thead>
          <tr>
            {showCodeColumn ? <th>Код</th> : null}
            <th>Тип</th>
            {showCocRankColumn ? <th>COC Rank</th> : null}
            <th>Номер</th>
            <th>Кем выдан</th>
            <th>Дата выдачи</th>
            <th>Дата окончания</th>
            <th className="scan-col">Скан</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const relationId = getId(item, ["certificate_id"]);
            const rowId = relationId ?? `canonical-${item.certificate_code || item.certificate_type}`;
            const isEditing = relationId != null && editingRowId === relationId;
            const draft = isEditing ? editDraft : item;
            const attachmentKey = `certificate:${relationId}`;
            const currentAttachment = relationId ? getRelationAttachment("certificate", relationId) : null;
            const busy = Boolean(attachmentBusy[attachmentKey]);
            const showValidityAssist = isEditing;
            const validityMode = draft.validityMode ?? inferValidityMode(draft);
            const rowClass = getRowExpiryClass ? getRowExpiryClass(item) : "";
            const resolvedTypeLabel =
              rowLabelMode === "medical"
                ? medicalRowType(item, diplomaSpecs)
                : rowLabelMode === "diploma"
                  ? diplomaRowType(item, diplomaSpecs)
                  : certificateRowType(item);
            const typeLocked = lockCanonicalType && Boolean(resolvedTypeLabel);
            const typeLabel = resolvedTypeLabel;
            const codeLabel =
              rowLabelMode === "medical"
                ? medicalRowCode(item, diplomaSpecs)
                : rowLabelMode === "diploma"
                  ? diplomaRowCode(item, diplomaSpecs)
                  : rowLabelMode === "sameAsType"
                    ? typeLabel
                    : certificateRowCode(item);
            const showCocRankCell = showCocRankColumn && isWorkingCocDiplomaRow(item);

            return (
              <React.Fragment key={rowId}>
                <tr
                  data-scan-target={relationId ? `certificate:${relationId}` : undefined}
                  className={`${rowClass} ${relationId && focusTarget === `certificate:${relationId}` ? "scan-target-highlight" : ""}`.trim()}
                >
                  {showCodeColumn ? (
                    <td className="muted-text">{codeLabel || "—"}</td>
                  ) : null}
                  <td>
                    <input
                      type="text"
                      value={isEditing ? draft.certificate_type || "" : typeLabel}
                      disabled={!isEditing || typeLocked}
                      title={typeLocked ? "Тип фиксирован для стандартной строки" : undefined}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          [section]: { ...prev[section], certificate_type: event.target.value },
                        }))
                      }
                    />
                  </td>
                  {showCocRankColumn ? (
                    <td>
                      {showCocRankCell ? (
                        <input
                          type="text"
                          value={draft.competency_rank || ""}
                          disabled={!isEditing}
                          placeholder="Chief Officer, Master, …"
                          onChange={(event) =>
                            setEditDrafts((prev) => ({
                              ...prev,
                              [section]: { ...prev[section], competency_rank: event.target.value },
                            }))
                          }
                        />
                      ) : (
                        <span className="muted-text">—</span>
                      )}
                    </td>
                  ) : null}
                  <td>
                    <input
                      type="text"
                      value={draft.certificate_number || ""}
                      disabled={!isEditing}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          [section]: { ...prev[section], certificate_number: event.target.value },
                        }))
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={draft.issuing_authority || ""}
                      disabled={!isEditing}
                      onChange={(event) =>
                        setEditDrafts((prev) => ({
                          ...prev,
                          [section]: { ...prev[section], issuing_authority: event.target.value },
                        }))
                      }
                    />
                  </td>
                  <td>
                    {isEditing ? (
                      <DateDdMmYyyyInput
                        value={draft.date_issued || ""}
                        onChange={(next) =>
                          setEditDrafts((prev) => ({
                            ...prev,
                            [section]: mergeCertificateDateChange(prev[section], "date_issued", next, validityMode),
                          }))
                        }
                      />
                    ) : (
                      displayValue(draft.date_issued)
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      draft.unlimited_validity === true || validityMode === VALIDITY_MODE.UNLIMITED ? (
                        <span className="certificate-expiry-unlimited">Unlimited</span>
                      ) : (
                        <DateDdMmYyyyInput
                          value={draft.expiry_date || ""}
                          onChange={(next) =>
                            setEditDrafts((prev) => ({
                              ...prev,
                              [section]: mergeCertificateDateChange(prev[section], "expiry_date", next, validityMode),
                            }))
                          }
                        />
                      )
                    ) : (
                      displayValue(formatCertificateExpiryDisplay(item))
                    )}
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
                          <span className="muted-text">Нет скана</span>
                        )}
                        <FileDropzone
                          compact
                          disabled={busy || !relationId}
                          testId={`dropzone-${section}-${relationId || rowId}`}
                          label={busy ? "Загрузка..." : currentAttachment ? "Заменить скан" : "Загрузить скан"}
                          onFile={(file) =>
                            relationId
                              ? onUploadRelationAttachment("certificate", relationId, file, currentAttachment)
                              : undefined
                          }
                        />
                        {currentAttachment?.attachment_id ? (
                          <button
                            type="button"
                            className="danger-btn scan-delete-btn"
                            disabled={busy}
                            onClick={() =>
                              onDeleteRelationAttachment("certificate", relationId, currentAttachment.attachment_id)
                            }
                          >
                            Удалить скан
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {attachmentErrors[attachmentKey] ? <div className="error">{attachmentErrors[attachmentKey]}</div> : null}
                  </td>
                  <td className="row-actions-cell">
                    <div className="actions-row">
                      {!canEditRelations ? (
                        <span className="muted-text">—</span>
                      ) : isEditing ? (
                        <>
                          <button type="button" onClick={() => onUpdate(relationId)}>
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
                          {onDelete && relationId && (canDeleteRow == null || canDeleteRow(item)) ? (
                            <button type="button" className="danger-btn" onClick={() => onDelete(relationId)}>
                              Удалить
                            </button>
                          ) : null}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
                {showValidityAssist ? (
                  <tr className="certificate-validity-row">
                    <td colSpan={(showCodeColumn ? 1 : 0) + (showCocRankColumn ? 1 : 0) + 6}>
                      <CertificateValidityControls
                        validityMode={validityMode}
                        draft={draft}
                        onValidityModeChange={(mode) =>
                          setEditDrafts((prev) => ({
                            ...prev,
                            [section]: { ...prev[section], validityMode: mode },
                          }))
                        }
                        onDraftChange={(cert) =>
                          setEditDrafts((prev) => ({
                            ...prev,
                            [section]: {
                              ...cert,
                              validityMode: cert.validityMode ?? prev[section].validityMode,
                            },
                          }))
                        }
                      />
                    </td>
                  </tr>
                ) : null}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
