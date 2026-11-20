import { apiClient } from "./api.js";

const path = candidate => `/candidates/${encodeURIComponent(candidate)}/document-intake`;
const batchPath = (candidate, batch) => `${path(candidate)}/${encodeURIComponent(batch)}`;
const submissionPath = (candidate, submission) => `${path(candidate)}/submissions/${encodeURIComponent(submission)}`;

export const DOCUMENT_UPLOAD_INBOX_CHANGED = "document-upload-inbox-changed";

function notifyInboxChanged() {
  window.dispatchEvent(new Event(DOCUMENT_UPLOAD_INBOX_CHANGED));
}

export async function fetchIntakeStatus(candidate, signal) {
  const { data } = await apiClient.get(`${path(candidate)}/status`, { signal, timeout: 5000 });
  return data?.enabled === true;
}

export async function fetchIntake(candidate, signal) {
  return (await apiClient.get(path(candidate), { signal })).data;
}

export async function uploadIntake(candidate, files, onUploadProgress, signal) {
  const body = new FormData();
  for (const file of files) body.append("files", file, file.name);
  return (await apiClient.post(path(candidate), body, { onUploadProgress, signal, timeout: 0 })).data;
}

export async function fetchIntakePreview(candidate, batch, file, page, signal) {
  return (await apiClient.get(`${batchPath(candidate, batch)}/files/${encodeURIComponent(file)}`, {
    responseType: "blob", params: { page }, signal,
  })).data;
}

export async function saveIntake(candidate, batch, documents, bulk, signal, finishSubmission = false) {
  const payload = { documents, bulk };
  if (finishSubmission) payload.finish_submission = true;
  const { data } = await apiClient.post(`${batchPath(candidate, batch)}/save`, payload, { timeout: 120000, signal });
  if (data.submission_finished) notifyInboxChanged();
  return data;
}

export async function discardIntake(candidate, batch, signal, external = false) {
  await apiClient.delete(batchPath(candidate, batch), { signal });
  if (external) notifyInboxChanged();
}

export async function retryIntake(candidate, batch, signal) {
  return (await apiClient.post(`${batchPath(candidate, batch)}/retry`, null, { signal })).data;
}

export async function getOrCreateUploadLink(candidate, signal) {
  return (await apiClient.post(`${path(candidate)}/upload-link`, null, { signal })).data.token;
}

export async function revokeUploadLink(candidate, signal) {
  await apiClient.delete(`${path(candidate)}/upload-link`, { signal });
}

export async function fetchIntakeSubmissions(candidate, signal) {
  return (await apiClient.get(`${path(candidate)}/submissions`, { signal, timeout: 5000 })).data;
}

export async function fetchIntakeNotifications(signal) {
  return (await apiClient.get("/document-upload/notifications", { signal, timeout: 5000 })).data;
}

export async function recognizeIntakeSubmission(candidate, submission, signal) {
  const { data } = await apiClient.post(`${submissionPath(candidate, submission)}/recognize`, null, { signal });
  notifyInboxChanged();
  return data;
}

export async function discardIntakeSubmission(candidate, submission, signal) {
  await apiClient.delete(submissionPath(candidate, submission), { signal });
  notifyInboxChanged();
}
