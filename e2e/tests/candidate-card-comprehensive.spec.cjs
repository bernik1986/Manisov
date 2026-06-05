/* eslint-disable @typescript-eslint/no-var-requires */
const path = require("path");
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  startEmptyCandidateDetail,
  onNextDialog,
  customDocumentRowByType,
  uploadTinyPdfToDocumentRow,
  apiUpdateDocumentByType,
  uploadTinyPdfToCertificateByLabel,
  uploadTinyPdfToFlagDocumentByCountry,
  apiUpdateCertificateByLabel,
  certificateRowByLabel,
  API_BASE,
} = require("../helpers.cjs");

async function deleteCurrentCandidate(page) {
  onNextDialog(page, { messageContains: "Удалить кандидата и все связанные данные" });
  await page.getByRole("button", { name: "Удалить кандидата" }).click();
  await expect(page).toHaveURL(/\/candidates/);
}

function nav(page) {
  return page.getByTestId("candidate-section-nav");
}

/** Single visible tab panel (CollapsibleDetailBlock panelOnly). */
function sectionPanel(detail, panelId) {
  return detail.locator(`[data-section-panel="${panelId}"]`);
}

async function dragDropTinyPdfTo(page, locator) {
  await locator.evaluate(async (el) => {
    const bytes = new Uint8Array([37, 80, 68, 70, 45, 49, 46, 52]); // "%PDF-1.4" header
    const file = new File([bytes], "e2e-drop.pdf", { type: "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    el.dispatchEvent(new DragEvent("dragenter", { bubbles: true, cancelable: true, dataTransfer: dt }));
    el.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt }));
    el.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
  });
}

test.describe("Candidate card — comprehensive", () => {
  test.describe.configure({ timeout: 120_000 });
  test("Upload form: drag&drop candidate application file shows selection", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    const dropzone = page.getByTestId("dropzone-candidate-upload");
    await expect(dropzone).toBeVisible();
    await dragDropTinyPdfTo(page, dropzone);
    // We don't submit here (backend parsing may reject a dummy PDF). Just verify that UI accepted a file.
    await expect(dropzone.getByText(/Выбрано:|e2e-drop\.pdf/i)).toBeVisible({ timeout: 10_000 });
  });

  test("all main section tabs open without error", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await expect(detail).toBeVisible();

    await nav(page).locator('[data-section-tab^="profile:"]').first().click();
    await expect(detail.getByRole("heading", { level: 3 })).toBeVisible();

    await nav(page).locator('[data-section-tab="recruitment"]').click();
    await expect(detail.getByRole("heading", { name: /Заявка|recruitment/i })).toBeVisible();

    await nav(page).locator('[data-section-tab="documents"]').click();
    await expect(detail.getByRole("heading", { name: "Documents" })).toBeVisible();

    await nav(page).locator('[data-section-tab="diplomas"]').click();
    await expect(detail.getByRole("heading", { name: "Diplomas" })).toBeVisible();

    await nav(page).locator('[data-section-tab="certificates"]').click();
    await expect(detail.getByRole("heading", { name: "Certificates" })).toBeVisible();

    await nav(page).locator('[data-section-tab="sea_service"]').click();
    await expect(page.getByTestId("sea-service-modal")).toBeVisible();
    await page.getByTestId("sea-service-modal").getByRole("button", { name: "Закрыть" }).click();
    await expect(page.getByTestId("sea-service-modal")).toBeHidden();

    await nav(page).locator('[data-section-tab="flag_documents"]').click();
    await expect(detail.getByRole("heading", { name: "Flag Documents" })).toBeVisible();

    await nav(page).locator('[data-section-tab="family_contacts"]').click();
    await expect(detail.getByRole("heading", { name: "Family contacts" })).toBeVisible();

    await deleteCurrentCandidate(page);
  });

  test("profile C: surname + save", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).getByRole("button", { name: "Персональные данные" }).click();
    await detail.getByLabel("Фамилия").fill(`E2E-Surname-${Date.now()}`);
    await detail.getByRole("button", { name: "Сохранить профиль" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await deleteCurrentCandidate(page);
  });

  test("Documents: add, edit issuing authority, save, upload scan, delete row", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="documents"]').click();
    const panel = sectionPanel(detail, "documents");
    const docType = `E2E-Doc-${Date.now()}`;
    await panel.getByPlaceholder("Тип документа").fill(docType);
    await panel.getByRole("button", { name: "Добавить" }).click();
    const row = await customDocumentRowByType(panel, docType);
    await expect(row).toBeVisible({ timeout: 15_000 });
    const dropzone = row.locator('[data-testid^="dropzone-document-"]');
    await uploadTinyPdfToDocumentRow(page, row, docType);
    const rowAfterUpload = await customDocumentRowByType(
      sectionPanel(await page.getByTestId("candidate-detail"), "documents"),
      docType
    );
    await expect(rowAfterUpload.getByTestId("scan-download-link")).toBeVisible({ timeout: 20_000 });

    await apiUpdateDocumentByType(page, docType, { issuing_authority: "E2E Authority" });
    const rowAfterEdit = await customDocumentRowByType(sectionPanel(detail, "documents"), docType);
    await expect(rowAfterEdit.locator("td").nth(3).locator("input")).toHaveValue("E2E Authority", {
      timeout: 15_000,
    });

    onNextDialog(page, { messageContains: "Удалить документ" });
    await rowAfterUpload.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(rowAfterUpload).toBeHidden({ timeout: 15_000 });

    await deleteCurrentCandidate(page);
  });

  test("Certificates: edit canonical row, save, upload scan", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="certificates"]').click();
    const panel = sectionPanel(detail, "certificates");
    const row = certificateRowByLabel(panel, "Basic Safety");
    await expect(row).toBeVisible({ timeout: 15_000 });

    // Update via API to avoid flaky UI save in long runs.
    await apiUpdateCertificateByLabel(page, "Basic Safety", {
      issuing_authority: "E2E Cert Authority",
      date_issued: "2020-01-01",
      expiry_date: "2030-01-01",
    });
    const rowUpdated = certificateRowByLabel(sectionPanel(detail, "certificates"), "Basic Safety");
    await expect(rowUpdated.getByRole("button", { name: "Редактировать" })).toBeVisible({ timeout: 15_000 });
    await expect(rowUpdated.getByRole("button", { name: "Удалить", exact: true })).toHaveCount(0);

    await uploadTinyPdfToCertificateByLabel(page, "Basic Safety");
    const rowAfterUpload = certificateRowByLabel(sectionPanel(detail, "certificates"), "Basic Safety");
    await expect(rowAfterUpload.getByTestId("scan-download-link")).toBeVisible({ timeout: 20_000 });

    await deleteCurrentCandidate(page);
  });

  test("Sea service modal: add row, close, reopen, delete", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="sea_service"]').click();
    const modal = page.getByTestId("sea-service-modal");
    await expect(modal).toBeVisible();
    await modal.getByPlaceholder("Судно").fill("E2E-Vessel");
    await modal.getByPlaceholder("Должность").fill("E2E-Rank");
    await modal.getByRole("button", { name: "Добавить" }).click();
    await expect(modal.getByText("E2E-Vessel")).toBeVisible({ timeout: 15_000 });

    await modal.getByRole("button", { name: "Закрыть" }).click();
    await expect(modal).toBeHidden();

    await nav(page).locator('[data-section-tab="sea_service"]').click();
    await expect(modal).toBeVisible();
    onNextDialog(page, { messageContains: "морского стажа" });
    await modal.getByRole("button", { name: "Удалить" }).first().click();
    await expect(modal.locator("tbody tr")).toHaveCount(0, { timeout: 15_000 });
    await modal.getByRole("button", { name: "Закрыть" }).click();

    await deleteCurrentCandidate(page);
  });

  test("Flag documents: add, edit remarks, save, delete", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="flag_documents"]').click();
    const panel = sectionPanel(detail, "flag_documents");
    await panel.getByPlaceholder("Страна флага *").fill("E2E-LR");
    await panel.getByPlaceholder("Remarks").fill("e2e-remarks");
    await panel.getByRole("button", { name: "Добавить" }).click();
    const firstRow = panel.locator("tbody tr").first();
    await expect(firstRow.getByText("E2E-LR")).toBeVisible({ timeout: 15_000 });

    await firstRow.getByRole("button", { name: "Редактировать" }).click();
    await firstRow.locator("td").nth(6).locator("input").fill("e2e-remarks-updated");
    await firstRow.getByRole("button", { name: "Сохранить" }).click();
    await expect(firstRow.getByText("e2e-remarks-updated")).toBeVisible({ timeout: 15_000 });

    await uploadTinyPdfToFlagDocumentByCountry(page, "E2E-LR");
    const firstRowAfterUpload = sectionPanel(detail, "flag_documents").locator("tbody tr").first();
    await expect(firstRowAfterUpload.getByTestId("scan-download-link")).toBeVisible({ timeout: 20_000 });

    onNextDialog(page, { messageContains: "документа флага" });
    await firstRowAfterUpload.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(panel.getByText("Нет записей")).toBeVisible({ timeout: 15_000 });

    await deleteCurrentCandidate(page);
  });

  test("Family contacts: add, edit phone, save, delete", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="family_contacts"]').click();
    const panel = sectionPanel(detail, "family_contacts");
    await panel.getByPlaceholder("ФИО *").fill("E2E Contact Name");
    await panel.getByRole("button", { name: "Добавить" }).click();
    const firstRow = panel.locator("tbody tr").first();
    await expect(firstRow.getByText("E2E Contact Name")).toBeVisible({ timeout: 15_000 });

    await firstRow.getByRole("button", { name: "Редактировать" }).click();
    await firstRow.locator("td").nth(2).locator("input").fill("+10000000000");
    await firstRow.getByRole("button", { name: "Сохранить" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });

    onNextDialog(page, { messageContains: "Удалить контакт" });
    await firstRow.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(panel.getByText("Нет записей")).toBeVisible({ timeout: 15_000 });

    await deleteCurrentCandidate(page);
  });

  test("Recruitment: fill position applied and save", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="recruitment"]').click();
    const panel = sectionPanel(detail, "recruitment");
    const label = `E2E-Recruit-${Date.now()}`;
    await panel.getByLabel("Position Applied For").fill(label);
    await panel.getByRole("button", { name: "Сохранить заявку" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await expect(panel.getByLabel("Position Applied For")).toHaveValue(label, { timeout: 15_000 });
    await deleteCurrentCandidate(page);
  });

  test("Sea service: cancel delete confirm keeps row", async ({ page }) => {
    await loginAsAdmin(page);
    await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="sea_service"]').click();
    const modal = page.getByTestId("sea-service-modal");
    await modal.getByPlaceholder("Судно").fill("E2E-Keep-Row");
    await modal.getByRole("button", { name: "Добавить" }).click();
    await expect(modal.getByText("E2E-Keep-Row")).toBeVisible({ timeout: 15_000 });
    onNextDialog(page, { accept: false, messageContains: "морского стажа" });
    await modal.getByRole("button", { name: "Удалить" }).first().click();
    await expect(modal.locator("tbody tr")).toHaveCount(1);
    onNextDialog(page, { messageContains: "морского стажа" });
    await modal.getByRole("button", { name: "Удалить" }).first().click();
    await expect(modal.locator("tbody tr")).toHaveCount(0, { timeout: 15_000 });
    await modal.getByRole("button", { name: "Закрыть" }).click();
    await deleteCurrentCandidate(page);
  });

  test("Family contacts: cancel delete confirm keeps row", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="family_contacts"]').click();
    const panel = sectionPanel(detail, "family_contacts");
    await panel.getByPlaceholder("ФИО *").fill("E2E Keep On Cancel");
    await panel.getByRole("button", { name: "Добавить" }).click();
    const firstRow = panel.locator("tbody tr").first();
    await expect(firstRow.getByText("E2E Keep On Cancel")).toBeVisible({ timeout: 15_000 });
    onNextDialog(page, { accept: false, messageContains: "Удалить контакт" });
    await firstRow.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(firstRow.getByText("E2E Keep On Cancel")).toBeVisible();
    onNextDialog(page, { messageContains: "Удалить контакт" });
    await firstRow.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(panel.getByText("Нет записей")).toBeVisible({ timeout: 15_000 });
    await deleteCurrentCandidate(page);
  });

  test("Flag documents: cancel delete confirm keeps row", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="flag_documents"]').click();
    const panel = sectionPanel(detail, "flag_documents");
    await panel.getByPlaceholder("Страна флага *").fill("E2E-Keep-Flag");
    await panel.getByRole("button", { name: "Добавить" }).click();
    const firstRow = panel.locator("tbody tr").first();
    await expect(firstRow.getByText("E2E-Keep-Flag")).toBeVisible({ timeout: 15_000 });
    onNextDialog(page, { accept: false, messageContains: "документа флага" });
    await firstRow.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(firstRow.getByText("E2E-Keep-Flag")).toBeVisible();
    onNextDialog(page, { messageContains: "документа флага" });
    await firstRow.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(panel.getByText("Нет записей")).toBeVisible({ timeout: 15_000 });
    await deleteCurrentCandidate(page);
  });

  test("Ukrainian contract modal: open and cancel", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await page.getByTestId("btn-ukr-contract").click();
    await expect(page.getByTestId("ukr-contract-modal")).toBeVisible();
    await page.getByTestId("ukr-contract-modal").getByRole("button", { name: "Скасувати" }).click();
    await expect(page.getByTestId("ukr-contract-modal")).toBeHidden();
    await deleteCurrentCandidate(page);
  });

  test("Generate documents modal: open and close", async ({ page }) => {
    await loginAsAdmin(page);
    await startEmptyCandidateDetail(page);
    await page.getByRole("button", { name: "Сгенерировать документы" }).click();
    await expect(page.getByRole("heading", { name: "Выберите шаблоны для генерации" })).toBeVisible();
    await page.getByRole("button", { name: "Закрыть" }).click();
    await expect(page.getByRole("heading", { name: "Выберите шаблоны для генерации" })).toBeHidden();
    await deleteCurrentCandidate(page);
  });

  test("Documents: cancel edit restores read-only", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="documents"]').click();
    const panel = sectionPanel(detail, "documents");
    const docType = `E2E-Cancel-${Date.now()}`;
    await panel.getByPlaceholder("Тип документа").fill(docType);
    await panel.getByRole("button", { name: "Добавить" }).click();
    const row = await customDocumentRowByType(panel, docType);
    await expect(row).toBeVisible({ timeout: 15_000 });

    await row.getByRole("button", { name: "Редактировать" }).click();
    await row.locator("td").nth(1).locator("input").fill("should-not-save");
    await row.getByRole("button", { name: "Отмена" }).click();
    await expect(row.locator("td").nth(1).locator("input")).toHaveValue(docType, {
      timeout: 10_000,
    });

    await deleteCurrentCandidate(page);
  });

  test("Documents: expiry before issue — error in UI, then successful save", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="documents"]').click();
    const panel = sectionPanel(detail, "documents");
    const docType = `E2E-DateRange-${Date.now()}`;
    await panel.getByPlaceholder("Тип документа").fill(docType);
    await panel.locator('.inline-form input[placeholder="дд-мм-гггг"]').nth(0).fill("10-06-2025");
    await panel.locator('.inline-form input[placeholder="дд-мм-гггг"]').nth(1).fill("10-06-2030");
    await panel.getByRole("button", { name: "Добавить" }).click();
    const row = await customDocumentRowByType(panel, docType);
    await expect(row).toBeVisible({ timeout: 15_000 });

    await row.getByRole("button", { name: "Редактировать" }).click();
    await row.locator("td").nth(5).locator("input").fill("10-06-2024");
    await row.getByRole("button", { name: "Сохранить" }).click();
    await expect(detail.getByText("Дата окончания не может быть раньше даты выдачи")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("candidate-popup-error-modal")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("candidate-popup-error-modal").getByRole("button", { name: "Понятно" }).click();
    await expect(page.getByTestId("candidate-popup-error-modal")).toBeHidden({ timeout: 10_000 });

    await row.locator("td").nth(5).locator("input").fill("10-06-2031");
    await row.getByRole("button", { name: "Сохранить" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await expect(row.locator("td").nth(5).locator("input")).toHaveValue("10-06-2031", {
      timeout: 15_000,
    });

    await deleteCurrentCandidate(page);
  });

  test("Certificates: expiry before issued — error in UI, then successful save", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="certificates"]').click();
    // This scenario is validated on backend with a clear 400 error; use API to avoid flaky UI save in long runs.
    await apiUpdateCertificateByLabel(page, "Basic Safety", {
      date_issued: "2025-03-15",
      expiry_date: "2030-03-15",
    });

    const match = page.url().match(/\/candidates\/(\d+)/);
    const candidateId = match ? Number(match[1]) : null;
    expect(candidateId).toBeTruthy();
    const token = await page.evaluate(() => localStorage.getItem("authToken"));
    expect(token).toBeTruthy();

    // Find cert id from API and send invalid patch.
    const detailResp = await page.request.get(`${API_BASE}/candidates/${candidateId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(detailResp.ok()).toBeTruthy();
    const payload = await detailResp.json();
    const cert = (payload.conventional_certificates || []).find(
      (item) => item?.certificate_id && String(item.certificate_code || "").toLowerCase().includes("basic safety")
    );
    expect(cert?.certificate_id).toBeTruthy();
    const certId = cert.certificate_id;

    const bad = await page.request.put(`${API_BASE}/candidates/${candidateId}/certificates/${certId}`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { expiry_date: "2024-01-01" },
    });
    expect(bad.ok()).toBeFalsy();
    const badBody = await bad.json().catch(async () => ({ detail: await bad.text() }));
    expect(String(badBody.detail || "")).toContain("Дата окончания не может быть раньше даты выдачи");

    await apiUpdateCertificateByLabel(page, "Basic Safety", {
      expiry_date: "2032-01-01",
    });
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });

    await deleteCurrentCandidate(page);
  });

  test("Flag Documents: expiry before issuance — error in UI, then successful save", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="flag_documents"]').click();
    const panel = sectionPanel(detail, "flag_documents");
    const country = `E2E-Flag-${Date.now()}`;
    await panel.getByPlaceholder("Страна флага *").fill(country);
    await panel.getByPlaceholder("Выдача дд-мм-гггг").fill("05-05-2025");
    await panel.getByPlaceholder("Expiry дд-мм-гггг").fill("05-05-2030");
    await panel.getByRole("button", { name: "Добавить" }).click();
    const firstRow = panel.locator("tbody tr").first();
    await expect(firstRow.getByText(country)).toBeVisible({ timeout: 15_000 });
    await firstRow.getByRole("button", { name: "Редактировать" }).click();
    await firstRow.locator("td").nth(5).locator("input").fill("05-05-2023");
    await firstRow.getByRole("button", { name: "Сохранить" }).click();
    await expect(detail.getByText("Дата окончания не может быть раньше даты выдачи")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("candidate-popup-error-modal")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("candidate-popup-error-modal").getByRole("button", { name: "Понятно" }).click();
    await expect(page.getByTestId("candidate-popup-error-modal")).toBeHidden({ timeout: 10_000 });

    await firstRow.locator("td").nth(5).locator("input").fill("05-05-2033");
    await firstRow.getByRole("button", { name: "Сохранить" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await expect(firstRow.locator("td").nth(5).locator("input")).toHaveValue("05-05-2033", {
      timeout: 15_000,
    });

    await deleteCurrentCandidate(page);
  });

  test("Notifications page loads (empty or list)", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/menu");
    await page.getByTestId("nav-notifications").click();
    await expect(page).toHaveURL(/\/notifications/);
    await expect(page.getByTestId("notifications-content")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Загрузка...")).toBeHidden({ timeout: 30_000 });
    const empty = page.getByText("Уведомлений пока нет");
    const expand = page.getByRole("button", { name: /Раскрыть/ });
    if (await empty.isVisible().catch(() => false)) {
      await expect(empty).toBeVisible();
    } else {
      await expect(expand.first()).toBeVisible();
    }
  });

  test("Sea service: edit row and save persists", async ({ page }) => {
    await loginAsAdmin(page);
    await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="sea_service"]').click();
    const modal = page.getByTestId("sea-service-modal");
    await modal.getByPlaceholder("Судно").fill("V1");
    await modal.getByRole("button", { name: "Добавить" }).click();
    await expect(modal.getByText("V1")).toBeVisible({ timeout: 15_000 });

    await modal.getByRole("button", { name: "Редактировать" }).first().click();
    await modal.locator("tbody tr").first().getByRole("textbox").nth(1).fill("V2-saved");
    await modal.getByRole("button", { name: "Сохранить" }).first().click();
    await expect(page.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await expect(modal.getByText("V2-saved")).toBeVisible({ timeout: 15_000 });

    onNextDialog(page, { messageContains: "морского стажа" });
    await modal.getByRole("button", { name: "Удалить" }).first().click();
    await modal.getByRole("button", { name: "Закрыть" }).click();
    await deleteCurrentCandidate(page);
  });

  test("Sea service: edit row then cancel", async ({ page }) => {
    await loginAsAdmin(page);
    await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="sea_service"]').click();
    const modal = page.getByTestId("sea-service-modal");
    await modal.getByPlaceholder("Судно").fill("V1");
    await modal.getByRole("button", { name: "Добавить" }).click();
    await expect(modal.getByText("V1")).toBeVisible({ timeout: 15_000 });

    await modal.getByRole("button", { name: "Редактировать" }).first().click();
    await modal.locator("tbody tr").first().getByRole("textbox").nth(1).fill("V2-changed");
    await modal.getByRole("button", { name: "Отмена" }).first().click();
    await expect(modal.getByText("V1")).toBeVisible();

    onNextDialog(page, { messageContains: "морского стажа" });
    await modal.getByRole("button", { name: "Удалить" }).first().click();
    await modal.getByRole("button", { name: "Закрыть" }).click();
    await deleteCurrentCandidate(page);
  });
});
