import axios from "axios";

function resolveApiBaseUrl() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured && configured.trim()) {
    return configured.replace(/\/+$/, "");
  }

  if (import.meta.env.DEV) {
    return "/api";
  }

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}

export const apiClient = axios.create({
  baseURL: resolveApiBaseUrl(),
  timeout: 10000,
});

const DOCUMENT_GENERATION_TIMEOUT_MS = 120000;

const TOKEN_REFRESH_THRESHOLD_SECONDS = 5 * 60;
let refreshPromise = null;

function clearAuthAndRedirectToLogin() {
  localStorage.removeItem("authToken");
  localStorage.removeItem("authUser");
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

function decodeJwtPayload(token) {
  try {
    const parts = String(token || "").split(".");
    if (parts.length < 2) return null;
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const json = atob(padded);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function getSecondsToExpiry(token) {
  const payload = decodeJwtPayload(token);
  const exp = Number(payload?.exp);
  if (!Number.isFinite(exp)) return null;
  return exp - Math.floor(Date.now() / 1000);
}

async function refreshAccessToken(currentToken) {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = apiClient
    .post(
      "/auth/refresh",
      {},
      {
        _skipAuthRefresh: true,
        headers: { Authorization: `Bearer ${currentToken}` },
      }
    )
    .then((response) => {
      const newToken = response?.data?.access_token;
      if (newToken) {
        localStorage.setItem("authToken", newToken);
      }
      if (response?.data?.user) {
        localStorage.setItem("authUser", JSON.stringify(response.data.user));
      }
      return newToken || currentToken;
    })
    .catch((error) => {
      clearAuthAndRedirectToLogin();
      throw error;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

apiClient.interceptors.request.use(async (config) => {
  const token = localStorage.getItem("authToken");
  if (!token) {
    return config;
  }
  const requestUrl = String(config?.url || "");
  const skipRefresh =
    Boolean(config?._skipAuthRefresh) ||
    requestUrl.includes("/auth/login") ||
    requestUrl.includes("/auth/refresh");

  let effectiveToken = token;
  const secondsToExpiry = getSecondsToExpiry(token);
  const tokenIsNearExpiry =
    secondsToExpiry !== null &&
    secondsToExpiry > 0 &&
    secondsToExpiry <= TOKEN_REFRESH_THRESHOLD_SECONDS;
  if (!skipRefresh && tokenIsNearExpiry) {
    effectiveToken = await refreshAccessToken(token);
  }

  config.headers = config.headers || {};
  config.headers.Authorization = `Bearer ${effectiveToken}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const requestUrl = String(error?.config?.url || "");
    const detail = String(error?.response?.data?.detail || "").toLowerCase();
    const isLoginRequest = requestUrl.includes("/auth/login");
    const isRefreshRequest = requestUrl.includes("/auth/refresh");
    const isAuthError =
      detail.includes("invalid or expired token") ||
      detail.includes("authentication required") ||
      detail.includes("user is inactive");
    if (status === 401 && isAuthError && !isLoginRequest && !isRefreshRequest) {
      clearAuthAndRedirectToLogin();
    }
    return Promise.reject(error);
  }
);

export async function login(payload) {
  const response = await apiClient.post("/auth/login", payload);
  return response.data;
}

export async function registerUser(payload) {
  const response = await apiClient.post("/auth/register", payload);
  return response.data;
}

export async function fetchUsers() {
  const response = await apiClient.get("/auth/users");
  return response.data;
}

export async function updateUserRole(userId, role) {
  const response = await apiClient.put(`/auth/users/${userId}/role`, { role });
  return response.data;
}

export async function updateUserPassword(userId, password) {
  const response = await apiClient.put(`/auth/users/${userId}/password`, { password });
  return response.data;
}

export async function updateUserActive(userId, isActive) {
  const response = await apiClient.put(`/auth/users/${userId}/active`, { is_active: isActive });
  return response.data;
}

export async function deleteUser(userId) {
  const response = await apiClient.delete(`/auth/users/${userId}`);
  return response.data;
}

export async function fetchNotifications(sent, limit) {
  const params = {};
  if (typeof sent === "boolean") {
    params.sent = sent;
  }
  if (typeof limit === "number" && limit > 0) {
    params.limit = limit;
  }
  const response = await apiClient.get("/notifications", { params });
  return response.data;
}

export async function fetchDashboardSummary() {
  const response = await apiClient.get("/dashboard/summary");
  return response.data;
}

export async function markNotificationSent(notificationId, sent = true) {
  const response = await apiClient.put(`/notifications/${notificationId}`, { sent });
  return response.data;
}

export async function fetchAuditLogs(params = {}) {
  const response = await apiClient.get("/audit-logs", { params });
  return response.data;
}

export async function fetchCandidates() {
  // Must match FastAPI list route: GET /candidates/ (without trailing slash GET returns 405).
  const response = await apiClient.get("/candidates/");
  return response.data;
}

/**
 * @param {object} [params]
 * @param {number} [params.page]
 * @param {number} [params.pageSize]
 * @param {string} [params.q]
 * @param {string} [params.position]
 * @param {string} [params.fleet]
 * @param {string|number} [params.companyId]
 */
export async function fetchCandidatesPaged({ page = 1, pageSize = 20, q, position, fleet, companyId } = {}) {
  const params = { page, page_size: pageSize };
  if (q && String(q).trim()) params.q = String(q).trim();
  if (position && String(position).trim()) params.position = String(position).trim();
  if (fleet && String(fleet).trim()) params.fleet = String(fleet).trim();
  if (companyId && String(companyId).trim()) params.company_id = String(companyId).trim();
  const response = await apiClient.get("/candidates/paged", { params });
  return response.data;
}

export async function createEmptyCandidate() {
  const response = await apiClient.post("/candidates");
  return response.data;
}

export async function fetchCandidateById(candidateId) {
  const response = await apiClient.get(`/candidates/${candidateId}`);
  return response.data;
}

export async function updateCandidate(candidateId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}`, payload);
  return response.data;
}

export async function uploadCandidatePhoto(candidateId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post(`/candidates/${candidateId}/photo`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function downloadCandidatePhoto(candidateId) {
  const response = await apiClient.get(`/candidates/${candidateId}/photo`, {
    responseType: "blob",
  });
  const contentType = String(response.headers?.["content-type"] || "image/jpeg");
  return response.data instanceof Blob && response.data.type
    ? response.data
    : new Blob([response.data], { type: contentType });
}

export async function deleteCandidatePhoto(candidateId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/photo`);
  return response.data;
}

export async function createCandidateComment(candidateId, commentText) {
  const response = await apiClient.post(`/candidates/${candidateId}/comments`, {
    comment_text: commentText,
  });
  return response.data;
}

export async function createApplication(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/applications`, payload);
  return response.data;
}

export async function updateApplication(candidateId, applicationId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/applications/${applicationId}`, payload);
  return response.data;
}

export async function deleteCandidate(candidateId) {
  const response = await apiClient.delete(`/candidates/${candidateId}`);
  return response.data;
}

export async function createDocument(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/documents`, payload);
  return response.data;
}

export async function updateDocument(candidateId, documentId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/documents/${documentId}`, payload);
  return response.data;
}

export async function deleteDocument(candidateId, documentId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/documents/${documentId}`);
  return response.data;
}

export async function createCertificate(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/certificates`, payload);
  return response.data;
}

export async function updateCertificate(candidateId, certificateId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/certificates/${certificateId}`, payload);
  return response.data;
}

export async function deleteCertificate(candidateId, certificateId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/certificates/${certificateId}`);
  return response.data;
}

export async function createSeaService(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/sea-service`, payload);
  return response.data;
}

export async function updateSeaService(candidateId, seaServiceId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/sea-service/${seaServiceId}`, payload);
  return response.data;
}

export async function deleteSeaService(candidateId, seaServiceId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/sea-service/${seaServiceId}`);
  return response.data;
}

export async function createFamilyContact(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/family-contacts`, payload);
  return response.data;
}

export async function updateFamilyContact(candidateId, contactId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/family-contacts/${contactId}`, payload);
  return response.data;
}

export async function deleteFamilyContact(candidateId, contactId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/family-contacts/${contactId}`);
  return response.data;
}

export async function createFlagDocument(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/flag-documents`, payload);
  return response.data;
}

export async function updateFlagDocument(candidateId, flagDocumentId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/flag-documents/${flagDocumentId}`, payload);
  return response.data;
}

export async function deleteFlagDocument(candidateId, flagDocumentId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/flag-documents/${flagDocumentId}`);
  return response.data;
}

export async function uploadCandidateFile(file, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("confirm_duplicate_update", options.confirmDuplicateUpdate ? "true" : "false");
  const response = await apiClient.post("/upload", formData, {
    timeout: 120000,
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function previewTextImport(text) {
  const response = await apiClient.post("/import/text/preview", { text });
  return response.data;
}

export async function createCandidateFromText(text) {
  const response = await apiClient.post("/import/text/create", { text });
  return response.data;
}

export async function uploadCvFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post("/upload_cv", formData, {
    timeout: 120000,
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function uploadAttachment(candidateId, file, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  if (options.attachmentType) {
    formData.append("attachment_type", options.attachmentType);
  }
  if (options.relationId !== undefined && options.relationId !== null) {
    formData.append("relation_id", String(options.relationId));
  }
  if (options.description) {
    formData.append("description", options.description);
  }

  const response = await apiClient.post(`/candidates/${candidateId}/attachments`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function deleteAttachment(attachmentId) {
  const response = await apiClient.delete(`/attachments/${attachmentId}`);
  return response.data;
}

export function getAttachmentDownloadUrl(attachmentId) {
  return `${apiClient.defaults.baseURL}/attachments/${attachmentId}/download`;
}

function parseContentDispositionFileName(disposition, fallback) {
  const header = String(disposition || "");
  const utf8Match = header.match(/filename\*=utf-8''([^;]+)/i);
  const plainMatch = header.match(/filename="?([^";]+)"?/i);
  const decodedUtf8 = utf8Match?.[1] ? decodeURIComponent(utf8Match[1]) : null;
  return decodedUtf8 || plainMatch?.[1] || fallback;
}

/** Authenticated fetch for opening scan preview in a new tab (plain href lacks JWT). */
export async function downloadAttachment(attachmentId) {
  const response = await apiClient.get(`/attachments/${attachmentId}/download`, {
    responseType: "blob",
  });
  const fileName = parseContentDispositionFileName(
    response.headers?.["content-disposition"],
    `attachment_${attachmentId}`
  );
  const contentType = String(response.headers?.["content-type"] || "application/octet-stream");
  const blob =
    response.data instanceof Blob && response.data.type
      ? response.data
      : new Blob([response.data], { type: contentType });
  return { blob, fileName, contentType };
}

export async function fetchTemplatesManager() {
  const response = await apiClient.get("/templates-manager");
  return response.data;
}

export async function createTemplateFolder(payload) {
  const response = await apiClient.post("/templates-manager/folders", payload);
  return response.data;
}

export async function renameTemplateFolder(folderId, payload) {
  const response = await apiClient.put(`/templates-manager/folders/${folderId}`, payload);
  return response.data;
}

export async function deleteTemplateFolder(folderId) {
  const response = await apiClient.delete(`/templates-manager/folders/${folderId}`);
  return response.data;
}

export async function uploadTemplateFile(folderId, file) {
  const formData = new FormData();
  formData.append("folder_id", String(folderId));
  formData.append("file", file);
  const response = await apiClient.post("/templates-manager/files", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function renameTemplateFile(fileId, payload) {
  const response = await apiClient.put(`/templates-manager/files/${fileId}`, payload);
  return response.data;
}

export async function deleteTemplateFile(fileId) {
  const response = await apiClient.delete(`/templates-manager/files/${fileId}`);
  return response.data;
}

export async function downloadTemplateFile(fileId) {
  const response = await apiClient.get(`/templates-manager/files/${fileId}/download`, {
    responseType: "blob",
  });
  const disposition = String(response.headers?.["content-disposition"] || "");
  const utf8Match = disposition.match(/filename\*=utf-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
  const decodedUtf8 = utf8Match?.[1] ? decodeURIComponent(utf8Match[1]) : null;
  const fileName = decodedUtf8 || plainMatch?.[1] || `template_${fileId}`;
  return { blob: response.data, fileName };
}

export async function fetchCompaniesManager() {
  const response = await apiClient.get("/companies-manager");
  return response.data;
}

export async function createCompanyFolder(payload) {
  const response = await apiClient.post("/companies-manager/folders", payload);
  return response.data;
}

export async function renameCompanyFolder(folderId, payload) {
  const response = await apiClient.put(`/companies-manager/folders/${folderId}`, payload);
  return response.data;
}

export async function deleteCompanyFolder(folderId) {
  const response = await apiClient.delete(`/companies-manager/folders/${folderId}`);
  return response.data;
}

export async function createCompany(payload) {
  const response = await apiClient.post("/companies-manager/companies", payload);
  return response.data;
}

export async function updateCompany(companyId, payload) {
  const response = await apiClient.put(`/companies-manager/companies/${companyId}`, payload);
  return response.data;
}

export async function deleteCompany(companyId) {
  const response = await apiClient.delete(`/companies-manager/companies/${companyId}`);
  return response.data;
}

export async function createVessel(payload) {
  const response = await apiClient.post("/companies-manager/vessels", payload);
  return response.data;
}

export async function updateVessel(vesselId, payload) {
  const response = await apiClient.put(`/companies-manager/vessels/${vesselId}`, payload);
  return response.data;
}

export async function deleteVessel(vesselId) {
  const response = await apiClient.delete(`/companies-manager/vessels/${vesselId}`);
  return response.data;
}

/** Excel columns: Company, IMO, Vessel name (same as scripts/import_vessels_from_xlsx.py). */
export async function fetchCompanySalaryRanks(companyId) {
  const response = await apiClient.get(`/companies-manager/companies/${companyId}/salary-ranks`);
  return response.data;
}

export async function fetchCompanySalaryTemplates(companyId) {
  const response = await apiClient.get(`/companies-manager/companies/${companyId}/salary-templates`);
  return response.data;
}

export async function createSalaryTemplate(payload) {
  const response = await apiClient.post("/companies-manager/salary-templates", payload);
  return response.data;
}

export async function updateSalaryTemplate(templateId, payload) {
  const response = await apiClient.put(`/companies-manager/salary-templates/${templateId}`, payload);
  return response.data;
}

export async function deleteSalaryTemplate(templateId) {
  const response = await apiClient.delete(`/companies-manager/salary-templates/${templateId}`);
  return response.data;
}

export async function previewSalaryCalculation(candidateId, payload) {
  const response = await apiClient.post(`/candidates/${candidateId}/salary-calculator/preview`, payload);
  return response.data;
}

export async function saveSalaryCalculation(candidateId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/salary-calculator`, payload);
  return response.data;
}

export async function resetSalaryCalculation(candidateId) {
  const response = await apiClient.delete(`/candidates/${candidateId}/salary-calculator`);
  return response.data;
}

export async function saveCandidateContract(candidateId, payload) {
  const response = await apiClient.put(`/candidates/${candidateId}/contract`, payload);
  return response.data;
}

export async function fetchContractTemplates() {
  const response = await apiClient.get("/templates-manager/contracts-folder");
  return response.data;
}

export async function importCompaniesFromXlsx(file, folderId = null) {
  const formData = new FormData();
  formData.append("file", file);
  if (folderId != null && folderId !== "") {
    formData.append("folder_id", String(folderId));
  }
  const response = await apiClient.post("/companies-manager/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/** Salary Scale.xlsx — sheets DryLog / Chandris (see salary_scale_xlsx_import.py). */
export async function importSalaryScaleFromXlsx(file, companySlug = null) {
  const formData = new FormData();
  formData.append("file", file);
  if (companySlug && String(companySlug).trim()) {
    formData.append("company_slug", String(companySlug).trim().toLowerCase());
  }
  const response = await apiClient.post("/companies-manager/salary-scale/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
  return response.data;
}

/** Path segments with `/` (%2F) often break routers — backend resolves managed files by ?template_file_id. */
export function templatePathSegmentForGenerateApi(templateName, templateFileId) {
  if (templateFileId != null && templateFileId !== undefined && !Number.isNaN(Number(templateFileId))) {
    return "managed-template";
  }
  const raw = String(templateName || "");
  const basename = raw.split(/[/\\]/).pop() || raw;
  return basename;
}

export async function generateCandidateDocument(
  candidateId,
  templateName,
  templateFileId = null,
  options = {}
) {
  const pathSegment = templatePathSegmentForGenerateApi(templateName, templateFileId);
  const encodedTemplateName = encodeURIComponent(pathSegment);
  const params = new URLSearchParams();
  if (templateFileId !== null && templateFileId !== undefined) {
    params.set("template_file_id", String(Number(templateFileId)));
  }
  if (options.contractsOnly) {
    params.set("contracts_only", "true");
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  try {
    const response = await apiClient.post(
      `/candidates/${candidateId}/generate/${encodedTemplateName}${query}`,
      null,
      {
        responseType: "blob",
        timeout: DOCUMENT_GENERATION_TIMEOUT_MS,
      }
    );
    const disposition = String(response.headers?.["content-disposition"] || "");
    const utf8Match = disposition.match(/filename\*=utf-8''([^;]+)/i);
    const plainMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
    const decodedUtf8 = utf8Match?.[1] ? decodeURIComponent(utf8Match[1]) : null;
    const fileName = decodedUtf8 || plainMatch?.[1] || `candidate_${candidateId}_${templateName}`;
    return { blob: response.data, fileName };
  } catch (error) {
    let parsedDetail = null;
    try {
      const contentType = String(error?.response?.headers?.["content-type"] || "");
      const data = error?.response?.data;
      if (data instanceof Blob && contentType.includes("application/json")) {
        const text = await data.text();
        parsedDetail = JSON.parse(text)?.detail || null;
      } else if (typeof data === "string") {
        parsedDetail = JSON.parse(data)?.detail || null;
      } else if (data && typeof data === "object") {
        parsedDetail = data.detail || null;
      }
    } catch (_) {
      parsedDetail = null;
    }
    if (parsedDetail && error?.response) {
      error.response.data = { ...(error.response.data || {}), detail: parsedDetail };
    }
    throw error;
  }
}

export async function buildSubmissionPack(candidateId, payload) {
  try {
    const response = await apiClient.post(`/candidates/${candidateId}/submission-pack`, payload, {
      responseType: "blob",
      timeout: DOCUMENT_GENERATION_TIMEOUT_MS,
    });
    const disposition = String(response.headers?.["content-disposition"] || "");
    const utf8Match = disposition.match(/filename\*=utf-8''([^;]+)/i);
    const plainMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
    const decodedUtf8 = utf8Match?.[1] ? decodeURIComponent(utf8Match[1]) : null;
    const fileName = decodedUtf8 || plainMatch?.[1] || `PODACHA_${candidateId}.zip`;
    return { blob: response.data, fileName };
  } catch (error) {
    let parsedDetail = null;
    try {
      const contentType = String(error?.response?.headers?.["content-type"] || "");
      const data = error?.response?.data;
      if (data instanceof Blob && contentType.includes("application/json")) {
        const text = await data.text();
        parsedDetail = JSON.parse(text)?.detail || null;
      } else if (typeof data === "string") {
        parsedDetail = JSON.parse(data)?.detail || null;
      } else if (data && typeof data === "object") {
        parsedDetail = data.detail || null;
      }
    } catch (_) {
      parsedDetail = null;
    }
    if (parsedDetail && error?.response) {
      error.response.data = { detail: parsedDetail };
    }
    throw error;
  }
}
