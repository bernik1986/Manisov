import React, { useState } from "react";
import { deleteAttachment, uploadAttachment } from "../api";
import FileDropzone from "./FileDropzone";
import ScanDownloadLink from "./ScanDownloadLink";

function getRelationAttachment(attachments, attachmentType, relationId) {
  return attachments.find(
    (item) =>
      item.source === attachmentType &&
      typeof item.description === "string" &&
      item.description.includes(`${attachmentType}:${relationId}`)
  );
}

function AttachmentRow({ candidateId, item, attachmentType, attachments, onChanged }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const relationId = item.id;
  const currentAttachment = getRelationAttachment(attachments, attachmentType, relationId);
  const hasAttachment = Boolean(currentAttachment);

  return (
    <tr>
      <td>{item.label}</td>
      <td>
        {hasAttachment ? (
          <ScanDownloadLink
            attachmentId={currentAttachment.attachment_id}
            fileName={currentAttachment.file_name}
          />
        ) : (
          <span className="muted-text">Файл не загружен</span>
        )}
      </td>
      <td className="actions-row">
        <FileDropzone
          disabled={busy}
          testId={`dropzone-${attachmentType}-${relationId}`}
          label={busy ? "Загрузка..." : hasAttachment ? "Заменить файл" : "Добавить файл"}
          onFile={async (file) => {
            setBusy(true);
            setError("");
            try {
              if (hasAttachment && currentAttachment?.attachment_id) {
                await deleteAttachment(currentAttachment.attachment_id);
              }
              await uploadAttachment(candidateId, file, {
                attachmentType,
                relationId,
                description: `${attachmentType}:${relationId}`,
              });
              await onChanged();
            } catch (requestError) {
              setError("Не удалось загрузить файл");
            } finally {
              setBusy(false);
            }
          }}
        />
        {hasAttachment ? (
          <button
            type="button"
            className="danger-btn"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await deleteAttachment(currentAttachment.attachment_id);
                await onChanged();
              } catch (requestError) {
                setError("Не удалось удалить файл");
              } finally {
                setBusy(false);
              }
            }}
          >
            Удалить
          </button>
        ) : null}
      </td>
      <td>{error ? <span className="error">{error}</span> : null}</td>
    </tr>
  );
}

export default function AttachmentsSection({ candidateId, documents, certificates, attachments, onChanged }) {
  const documentItems = documents.map((doc) => ({
    id: doc.document_id || doc.id,
    label: `Документ: ${doc.document_type || "Без названия"}`,
  }));
  const certificateItems = certificates.map((cert) => ({
    id: cert.certificate_id || cert.id,
    label: `Сертификат: ${cert.certificate_type || "Без названия"}`,
  }));

  return (
    <div className="detail-block">
      <h2>Сканы</h2>
      <table className="candidate-table">
        <thead>
          <tr>
            <th>Связь</th>
            <th>Файл</th>
            <th>Действия</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {documentItems.map((item) => (
            <AttachmentRow
              key={`document-${item.id}`}
              candidateId={candidateId}
              item={item}
              attachmentType="document"
              attachments={attachments}
              onChanged={onChanged}
            />
          ))}
          {certificateItems.map((item) => (
            <AttachmentRow
              key={`certificate-${item.id}`}
              candidateId={candidateId}
              item={item}
              attachmentType="certificate"
              attachments={attachments}
              onChanged={onChanged}
            />
          ))}
          {documentItems.length === 0 && certificateItems.length === 0 ? (
            <tr>
              <td colSpan={4} className="empty-row">
                Нет документов и сертификатов для загрузки сканов
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
