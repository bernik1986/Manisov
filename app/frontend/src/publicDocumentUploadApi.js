import { apiClient } from "./api.js";

async function request(token, options) {
  const response = await fetch(`${apiClient.defaults.baseURL}/public/document-upload`, {
    cache: "no-store",
    credentials: "omit",
    redirect: "error",
    referrerPolicy: "no-referrer",
    headers: { "X-Document-Upload-Token": token },
    ...options,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) {
    const detail = typeof data?.detail === "string" ? data.detail : {
      404: "upload_link_unavailable",
      410: "upload_link_unavailable",
      413: "batch_size_limit",
      429: "batch_busy",
    }[response.status];
    throw new Error(detail || "request_failed");
  }
  return data;
}

export function loadPublicDocumentUpload(token, signal) {
  return request(token, { signal });
}

export function sendPublicDocumentUpload(token, requestId, files, documents, signal) {
  const body = new FormData();
  body.append("manifest", JSON.stringify({
    request_id: requestId,
    documents: documents.map(({ typeKey, pages }) => ({ type_key: typeKey, page_count: pages.length })),
  }));
  for (const { file } of files) body.append("files", file, file.name);
  for (const { pages } of documents) {
    for (const { file } of pages) body.append("pages", file, file.name);
  }
  return request(token, { method: "POST", body, signal });
}
