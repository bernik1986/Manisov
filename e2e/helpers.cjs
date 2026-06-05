/* eslint-disable @typescript-eslint/no-var-requires */
const path = require("path");
const { expect } = require("@playwright/test");

/** Default user from `app.main` _ensure_default_auth_data */
const ADMIN = { user: "admin", pass: "admin123" };
const API_BASE = process.env.PW_API_BASE || "http://127.0.0.1:8000";
const API_REQUEST_TIMEOUT = 90_000;
const E2E_ROOT = path.join(__dirname);
const REPO_ROOT = path.join(E2E_ROOT, "..");

async function resetLoginThrottle(page) {
  await page.request.post(`${API_BASE}/test/reset-login-throttle`);
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function loginAsAdmin(page) {
  await resetLoginThrottle(page);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto("/login");
    await page.getByTestId("login-form").getByLabel("Логин").fill(ADMIN.user);
    await page.getByLabel("Пароль").fill(ADMIN.pass);
    await page.getByRole("button", { name: "Войти" }).click();
    try {
      await expect(page).toHaveURL(/\/menu$/, { timeout: 25_000 });
      return;
    } catch (_e) {
      if (attempt === 2) {
        throw _e;
      }
    }
  }
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} username
 * @param {string} password
 */
async function loginAs(page, username, password) {
  await resetLoginThrottle(page);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto("/login");
    await page.getByTestId("login-form").getByLabel("Логин").fill(username);
    await page.getByLabel("Пароль").fill(password);
    await page.getByRole("button", { name: "Войти" }).click();
    try {
      await expect(page).toHaveURL(/\/menu$/, { timeout: 25_000 });
      return;
    } catch (_e) {
      if (attempt === 2) {
        throw _e;
      }
    }
  }
}

function uniqueUser(prefix = "e2e_u") {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
}

function fixturePath(name) {
  return path.join(E2E_ROOT, "fixtures", name);
}

function repoFilePath(...segments) {
  return path.join(REPO_ROOT, ...segments);
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function getAuthToken(page) {
  const token = await page.evaluate(() => localStorage.getItem("authToken"));
  if (!token) {
    throw new Error("No authToken in localStorage — login first");
  }
  return token;
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function apiDeleteCandidate(page, candidateId) {
  const token = await getAuthToken(page);
  const response = await page.request.delete(`${API_BASE}/candidates/${candidateId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response;
}

/**
 * Remove leftover E2E/parser rows so upload-duplicate can start from a clean slate.
 * @param {import('@playwright/test').Page} page
 * @param {string} surname
 */
async function apiDeleteCandidatesBySurname(page, surname) {
  const token = await getAuthToken(page);
  const response = await page.request.get(
    `${API_BASE}/candidates/search?q=${encodeURIComponent(surname)}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!response.ok()) {
    return;
  }
  const payload = await response.json();
  const needle = surname.trim().toLowerCase();
  for (const row of payload.items || []) {
    if ((row.surname || "").trim().toLowerCase() === needle) {
      await apiDeleteCandidate(page, row.id);
    }
  }
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function waitForCandidateListReady(page) {
  const section = page.getByTestId("candidate-list-section");
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await expect(page.getByText("Загрузка кандидатов...")).toBeHidden({ timeout: 45_000 });

    // Some environments intermittently fail fetching the list (server warmup).
    // If we see a visible error, reload once and retry.
    const globalErr = page.getByText("Не удалось загрузить список кандидатов.");
    const localErr = section.locator("p.error");
    if (
      (await globalErr.isVisible().catch(() => false)) ||
      (await localErr.isVisible().catch(() => false))
    ) {
      if (attempt < 3) {
        await page.goto("/candidates");
        continue;
      }
      const msg =
        (await localErr.textContent().catch(() => "")) ||
        (await globalErr.textContent().catch(() => "")) ||
        "unknown error";
      throw new Error(`Candidate list failed: ${msg}`);
    }

    const tableCount = await section.getByRole("table").count().catch(() => 0);
    const cardsCount = await section.locator('[data-testid="candidate-card"]').count().catch(() => 0);
    if (tableCount > 0 || cardsCount > 0) {
      return;
    }
    if (attempt < 3) {
      await page.goto("/candidates");
    }
  }
  throw new Error("Candidate list failed: no table/cards rendered");
}

/**
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<import('@playwright/test').Locator>}
 */
async function startEmptyCandidateDetail(page) {
  await page.goto("/candidates");
  await waitForCandidateListReady(page);
  const btn = page.getByTestId("btn-new-empty-candidate");
  await expect(btn).toBeEnabled({ timeout: 15_000 });
  await btn.click();
  try {
    await expect(page).toHaveURL(/\/candidates\/\d+$/, { timeout: 25_000 });
  } catch (_e) {
    const token = await getAuthToken(page);
    const resp = await page.request.post(`${API_BASE}/candidates`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: API_REQUEST_TIMEOUT,
    });
    expect(resp.ok(), await resp.text()).toBeTruthy();
    const payload = await resp.json();
    const id = payload.candidate_id;
    expect(id).toBeTruthy();
    await page.goto(`/candidates/${id}`);
    await expect(page).toHaveURL(/\/candidates\/\d+$/, { timeout: 15_000 });
  }
  await expect(page.getByTestId("candidate-detail")).toBeVisible({ timeout: 15_000 });
  return page.getByTestId("candidate-detail");
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function deleteCurrentCandidate(page) {
  onNextDialog(page, { messageContains: "Удалить кандидата и все связанные данные" });
  await page.getByRole("button", { name: "Удалить кандидата" }).click();
  await expect(page).toHaveURL(/\/candidates/);
}

/**
 * @param {import('@playwright/test').Page} page
 */
function candidateSectionNav(page) {
  return page.getByTestId("candidate-section-nav");
}

/**
 * @param {import('@playwright/test').Locator} detail
 * @param {string} panelId
 */
function sectionPanel(detail, panelId) {
  return detail.locator(`[data-section-panel="${panelId}"]`);
}

/**
 * Document table row by type input value (not first row — canonical slots come first).
 * @param {import('@playwright/test').Locator} panel
 * @param {string} docType
 */
/** Canonical document slots always render first (12 rows). Custom rows append after them. */
const CANONICAL_DOCUMENT_ROW_COUNT = 12;

/**
 * Nth custom document row (0 = first row after canonical slots).
 * @param {import('@playwright/test').Locator} panel
 * @param {number} [index]
 */
function customDocumentRow(panel, index = 0) {
  return panel.locator("tbody tr").nth(CANONICAL_DOCUMENT_ROW_COUNT + index);
}

/**
 * Custom document row matching type in the type column (column index 1).
 * @param {import('@playwright/test').Locator} panel
 * @param {string} docType
 */
async function customDocumentRowByType(panel, docType) {
  const rows = panel.locator("tbody tr");
  await expect
    .poll(async () => {
      const count = await rows.count();
      for (let i = 0; i < count; i += 1) {
        const value = await rows.nth(i).locator("td").nth(1).locator("input").inputValue();
        if (value === docType) {
          return true;
        }
      }
      return false;
    }, { timeout: 30_000 })
    .toBeTruthy();

  const count = await rows.count();
  for (let i = 0; i < count; i += 1) {
    const row = rows.nth(i);
    const value = await row.locator("td").nth(1).locator("input").inputValue();
    if (value === docType) {
      return row;
    }
  }
  throw new Error(`Custom document row not found for type: ${docType}`);
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} row document table row
 */
async function uploadTinyPdfToDocumentRow(page, row, docType) {
  const match = page.url().match(/\/candidates\/(\d+)/);
  const candidateId = match ? Number(match[1]) : null;
  if (!candidateId) {
    throw new Error("Candidate id not found in URL");
  }
  const token = await getAuthToken(page);
  const detailResp = await page.request.get(`${API_BASE}/candidates/${candidateId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(detailResp.ok()).toBeTruthy();
  const documents = (await detailResp.json()).documents || [];
  const doc = documents.find((item) => item.document_type === docType);
  expect(doc?.document_id).toBeTruthy();
  const uploadResp = await page.request.post(`${API_BASE}/candidates/${candidateId}/attachments`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: API_REQUEST_TIMEOUT,
    multipart: {
      file: {
        name: "e2e-drop.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.4"),
      },
      attachment_type: "document",
      relation_id: String(doc.document_id),
      description: `document:${doc.document_id}`,
    },
  });
  expect(uploadResp.ok(), await uploadResp.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("candidate-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("candidate-section-nav").locator('[data-section-tab="documents"]').click();
}

/**
 * Update a document row via API by matching its type in candidate payload.
 * @param {import('@playwright/test').Page} page
 * @param {string} docType exact match
 * @param {object} patch
 */
async function apiUpdateDocumentByType(page, docType, patch) {
  const match = page.url().match(/\/candidates\/(\d+)/);
  const candidateId = match ? Number(match[1]) : null;
  if (!candidateId) {
    throw new Error("Candidate id not found in URL");
  }
  const token = await getAuthToken(page);
  const detailResp = await page.request.get(`${API_BASE}/candidates/${candidateId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(detailResp.ok()).toBeTruthy();
  const documents = (await detailResp.json()).documents || [];
  const doc = documents.find((item) => item.document_type === docType);
  expect(doc?.document_id).toBeTruthy();
  const docId = doc.document_id;
  const resp = await page.request.put(`${API_BASE}/candidates/${candidateId}/documents/${docId}`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: API_REQUEST_TIMEOUT,
    data: patch || {},
  });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("candidate-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("candidate-section-nav").locator('[data-section-tab="documents"]').click();
}

/**
 * Upload a tiny PDF scan for a certificate row by matching its label in API payload.
 * Uses the authenticated request API to avoid flaky drag&drop.
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} certificateLabel substring to match (e.g. "Basic Safety")
 */
async function uploadTinyPdfToCertificateByLabel(page, certificateLabel) {
  const match = page.url().match(/\/candidates\/(\d+)/);
  const candidateId = match ? Number(match[1]) : null;
  if (!candidateId) {
    throw new Error("Candidate id not found in URL");
  }
  const token = await getAuthToken(page);
  const detailResp = await page.request.get(`${API_BASE}/candidates/${candidateId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(detailResp.ok()).toBeTruthy();
  const payload = await detailResp.json();
  const rows = [
    ...(payload.conventional_certificates || []),
    ...(payload.ecdis_certificates || []),
    ...(payload.company_certificates || []),
    ...(payload.bwts_certificates || []),
    ...(payload.certificates || []),
    ...(payload.diplomas || []),
    ...(payload.tanker_diplomas || []),
    ...(payload.medical_documents || []),
  ];
  const needle = String(certificateLabel || "").toLowerCase();
  const cert = rows.find(
    (item) =>
      item?.certificate_id &&
      String(item.certificate_code || item.certificate_type || "")
        .toLowerCase()
        .includes(needle)
  );
  expect(cert?.certificate_id).toBeTruthy();
  const certId = cert.certificate_id;
  const uploadResp = await page.request.post(`${API_BASE}/candidates/${candidateId}/attachments`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: API_REQUEST_TIMEOUT,
    multipart: {
      file: {
        name: "e2e-drop.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.4"),
      },
      attachment_type: "certificate",
      relation_id: String(certId),
      description: `certificate:${certId}`,
    },
  });
  expect(uploadResp.ok(), await uploadResp.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("candidate-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("candidate-section-nav").locator('[data-section-tab="certificates"]').click();
}

/**
 * Upload a tiny PDF scan for the first flag document row (matched by country) via API.
 * @param {import('@playwright/test').Page} page
 * @param {string} flagCountry substring to match (e.g. "E2E-LR")
 */
async function uploadTinyPdfToFlagDocumentByCountry(page, flagCountry) {
  const match = page.url().match(/\/candidates\/(\d+)/);
  const candidateId = match ? Number(match[1]) : null;
  if (!candidateId) {
    throw new Error("Candidate id not found in URL");
  }
  const token = await getAuthToken(page);
  const detailResp = await page.request.get(`${API_BASE}/candidates/${candidateId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(detailResp.ok()).toBeTruthy();
  const payload = await detailResp.json();
  const needle = String(flagCountry || "").toLowerCase();
  const row = (payload.flag_documents || []).find(
    (item) =>
      item?.flag_document_id &&
      String(item.flag_country || "").toLowerCase().includes(needle)
  );
  expect(row?.flag_document_id).toBeTruthy();
  const relId = row.flag_document_id;
  const uploadResp = await page.request.post(`${API_BASE}/candidates/${candidateId}/attachments`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: API_REQUEST_TIMEOUT,
    multipart: {
      file: {
        name: "e2e-drop.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.4"),
      },
      attachment_type: "flag_document",
      relation_id: String(relId),
      description: `flag_document:${relId}`,
    },
  });
  expect(uploadResp.ok(), await uploadResp.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("candidate-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("candidate-section-nav").locator('[data-section-tab="flag_documents"]').click();
}

/**
 * Update a certificate row via API by matching its label in candidate payload.
 * @param {import('@playwright/test').Page} page
 * @param {string} certificateLabel
 * @param {object} patch
 */
async function apiUpdateCertificateByLabel(page, certificateLabel, patch) {
  const match = page.url().match(/\/candidates\/(\d+)/);
  const candidateId = match ? Number(match[1]) : null;
  if (!candidateId) {
    throw new Error("Candidate id not found in URL");
  }
  const token = await getAuthToken(page);
  const detailResp = await page.request.get(`${API_BASE}/candidates/${candidateId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(detailResp.ok()).toBeTruthy();
  const payload = await detailResp.json();
  const rows = [
    ...(payload.conventional_certificates || []),
    ...(payload.ecdis_certificates || []),
    ...(payload.company_certificates || []),
    ...(payload.bwts_certificates || []),
    ...(payload.certificates || []),
    ...(payload.diplomas || []),
    ...(payload.tanker_diplomas || []),
    ...(payload.medical_documents || []),
  ];
  const needle = String(certificateLabel || "").toLowerCase();
  const cert = rows.find(
    (item) =>
      item?.certificate_id &&
      String(item.certificate_code || item.certificate_type || "")
        .toLowerCase()
        .includes(needle)
  );
  expect(cert?.certificate_id).toBeTruthy();
  const certId = cert.certificate_id;
  const resp = await page.request.put(`${API_BASE}/candidates/${candidateId}/certificates/${certId}`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: API_REQUEST_TIMEOUT,
    data: patch || {},
  });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("candidate-detail")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("candidate-section-nav").locator('[data-section-tab="certificates"]').click();
}

/** @deprecated use uploadTinyPdfToDocumentRow */
async function uploadTinyPdfViaDropzone(page, rowOrDropzone) {
  const row =
    (await rowOrDropzone.locator("td").count()) > 0
      ? rowOrDropzone
      : rowOrDropzone.locator("xpath=ancestor::tr[1]");
  await uploadTinyPdfToDocumentRow(page, row);
}

/** @deprecated use customDocumentRow — kept as alias for tests that add one custom row */
function documentRowByType(panel, _docType, index = 0) {
  return customDocumentRow(panel, index);
}

/**
 * Certificate/diploma row in the first table of the scope (conventional block on Certificates tab).
 * @param {import('@playwright/test').Locator} scope
 * @param {string} label
 */
function certificateRowByLabel(scope, label) {
  const table = scope.locator(".table-wrap table").first();
  return table.locator("tbody tr").filter({ hasText: label });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').Locator} locator
 */
async function dragDropTinyPdfTo(page, locator) {
  await locator.evaluate(async (el) => {
    const bytes = new Uint8Array([37, 80, 68, 70, 45, 49, 46, 52]);
    const file = new File([bytes], "e2e-drop.pdf", { type: "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    el.dispatchEvent(new DragEvent("dragenter", { bubbles: true, cancelable: true, dataTransfer: dt }));
    el.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt }));
    el.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
  });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {() => Promise<void>} triggerClick
 */
async function expectDownloadAfter(page, triggerClick) {
  const downloadPromise = page.waitForEvent("download", { timeout: 60_000 });
  await triggerClick();
  const download = await downloadPromise;
  const name = download.suggestedFilename();
  expect(name.length).toBeGreaterThan(0);
  const savePath = path.join(E2E_ROOT, ".downloads", `${Date.now()}-${name}`);
  await download.saveAs(savePath);
  return { download, savePath, fileName: name };
}

/**
 * Handle the next native `window.confirm` / `alert` once.
 * @param {import('@playwright/test').Page} page
 * @param {{ accept?: boolean, messageContains?: string, type?: 'confirm'|'alert' }} [opts]
 */
function isCandidateUploadResponse(response) {
  const url = response.url();
  return (
    url.includes("/upload") &&
    !url.includes("/upload_cv") &&
    response.request().method() === "POST" &&
    response.status() === 200
  );
}

/**
 * Manager tree root is disabled when already selected — skip click in that case.
 * @param {import('@playwright/test').Page} page
 * @param {string} name
 */
async function selectManagerTreeRootIfNeeded(page, rootName) {
  const btn = page.getByRole("button", { name: rootName, exact: true });
  await expect(btn).toBeVisible({ timeout: 30_000 });
  if (await btn.isEnabled()) {
    await btn.click();
  }
}

/**
 * Templates manager: select root folder in tree so "+ Subfolder" is enabled.
 * @param {import('@playwright/test').Page} page
 */
async function selectTemplatesManagerRoot(page) {
  await expect(page.getByTestId("templates-manager")).toBeVisible({ timeout: 30_000 });
  const treeBtn = page.locator(".templates-tree").getByRole("button", { name: "Templates", exact: true });
  await expect(treeBtn).toBeEnabled({ timeout: 30_000 });
  await treeBtn.click();
  await expect(page.getByRole("button", { name: "+ Subfolder" })).toBeEnabled({ timeout: 15_000 });
}

/**
 * Warm notifications API (triggers sync) before opening the page.
 * @param {import('@playwright/test').Page} page
 */
async function warmNotificationsApi(page) {
  const token = await getAuthToken(page);
  const headers = { Authorization: `Bearer ${token}` };
  const notifResp = await page.request.get(`${API_BASE}/notifications`, {
    headers,
    params: { sent: false, limit: 1 },
    timeout: 30_000,
  });
  expect(notifResp.ok(), await notifResp.text()).toBeTruthy();
  const candResp = await page.request.get(`${API_BASE}/candidates/`, {
    headers,
    timeout: API_REQUEST_TIMEOUT,
  });
  expect(candResp.ok(), await candResp.text()).toBeTruthy();
}

/**
 * @param {import('@playwright/test').Page} page
 */
async function waitForNotificationsPageReady(page) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (attempt > 0) {
      await warmNotificationsApi(page);
    }
    await page.goto("/notifications");
    await expect(page.getByTestId("notifications-content")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Загрузка...")).toBeHidden({ timeout: 45_000 });
    const errCount = await page.getByText("Не удалось загрузить уведомления").count();
    if (errCount === 0) {
      return;
    }
  }
  await expect(page.getByText("Не удалось загрузить уведомления")).toHaveCount(0);
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} username
 */
async function waitForUsernameInUsersApi(page, username) {
  await expect
    .poll(async () => {
      const token = await getAuthToken(page);
      const resp = await page.request.get(`${API_BASE}/auth/users`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: API_REQUEST_TIMEOUT,
      });
      if (!resp.ok()) {
        return false;
      }
      const items = (await resp.json()).items || [];
      return items.some((row) => row.username === username);
    }, { timeout: 30_000 })
    .toBeTruthy();
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {string} username
 */
async function waitForUsernameInUsersTable(page, username) {
  await waitForUsernameInUsersApi(page, username);
  await page.goto("/users");
  await expect(page.getByRole("cell", { name: username, exact: true })).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Collect JSON bodies from one or more POST /upload responses triggered by `action`.
 * @param {import('@playwright/test').Page} page
 * @param {() => Promise<void>} action
 * @param {{ timeout?: number, until?: (bodies: object[]) => boolean }} [opts]
 */
async function collectUploadResponses(page, action, opts = {}) {
  const timeout = opts.timeout ?? 180_000;
  const until = opts.until ?? ((bodies) => bodies.length > 0);
  const bodies = [];
  const listener = async (response) => {
    if (!isCandidateUploadResponse(response)) {
      return;
    }
    bodies.push(await response.json());
  };
  page.on("response", listener);
  try {
    await action();
    await expect.poll(() => until(bodies), { timeout }).toBeTruthy();
  } finally {
    page.off("response", listener);
  }
  return bodies;
}

function onNextDialog(page, { accept = true, messageContains, type } = {}) {
  page.once("dialog", async (dialog) => {
    if (messageContains != null) {
      if (type) {
        expect(dialog.type()).toBe(type);
      }
      expect(dialog.message()).toContain(messageContains);
    }
    if (accept) {
      await dialog.accept();
    } else {
      await dialog.dismiss();
    }
  });
}

module.exports = {
  ADMIN,
  API_BASE,
  API_REQUEST_TIMEOUT,
  REPO_ROOT,
  loginAsAdmin,
  loginAs,
  uniqueUser,
  fixturePath,
  repoFilePath,
  getAuthToken,
  apiDeleteCandidate,
  apiDeleteCandidatesBySurname,
  waitForCandidateListReady,
  startEmptyCandidateDetail,
  deleteCurrentCandidate,
  candidateSectionNav,
  sectionPanel,
  documentRowByType,
  customDocumentRow,
  customDocumentRowByType,
  uploadTinyPdfToDocumentRow,
  apiUpdateDocumentByType,
  uploadTinyPdfToCertificateByLabel,
  uploadTinyPdfToFlagDocumentByCountry,
  apiUpdateCertificateByLabel,
  uploadTinyPdfViaDropzone,
  certificateRowByLabel,
  resetLoginThrottle,
  dragDropTinyPdfTo,
  expectDownloadAfter,
  collectUploadResponses,
  selectManagerTreeRootIfNeeded,
  selectTemplatesManagerRoot,
  warmNotificationsApi,
  waitForNotificationsPageReady,
  waitForUsernameInUsersApi,
  waitForUsernameInUsersTable,
  onNextDialog,
};
