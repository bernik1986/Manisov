/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  startEmptyCandidateDetail,
  deleteCurrentCandidate,
  candidateSectionNav,
  sectionPanel,
  customDocumentRowByType,
  uploadTinyPdfToDocumentRow,
  dragDropTinyPdfTo,
  expectDownloadAfter,
  onNextDialog,
} = require("../helpers.cjs");

test.describe.configure({ timeout: 120_000 });

test.describe("PODACHA, downloads, scan preview, Ukrainian contract", () => {
  test("PODACHA: build ZIP when template and scan exist", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await candidateSectionNav(page).locator('[data-section-tab="documents"]').click();
    const panel = sectionPanel(detail, "documents");
    const docType = `E2E-Podacha-${Date.now()}`;
    await panel.getByPlaceholder("Тип документа").fill(docType);
    await panel.getByRole("button", { name: "Добавить" }).click();
    const row = await customDocumentRowByType(panel, docType);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await uploadTinyPdfToDocumentRow(page, row, docType);
    const rowAfterUpload = await customDocumentRowByType(panel, docType);
    await expect(rowAfterUpload.getByTestId("scan-download-link")).toBeVisible({ timeout: 20_000 });

    await page.getByTestId("btn-podacha").click();
    const modal = page.getByTestId("podacha-modal");
    await expect(modal).toBeVisible();
    await modal.locator(".podacha-field").nth(0).locator("input").fill("E2E Opening Vessel");
    await modal.locator(".podacha-field").nth(1).locator("input").fill("E2E Previous");

    await expect(modal.getByText("Загрузка шаблонов…")).toBeHidden({ timeout: 30_000 });
    const templateChecks = modal.locator(".podacha-section").filter({ hasText: "Шаблоны" }).locator('input[type="checkbox"]');
    const templateCount = await templateChecks.count();
    if (templateCount === 0) {
      test.skip(true, "No .docx templates in manager — run app once to seed Podacha");
      return;
    }
    await templateChecks.first().check();
    await modal
      .locator(".podacha-section")
      .filter({ hasText: "Сканы документов" })
      .locator('input[type="checkbox"]:enabled')
      .first()
      .check();

    const { fileName } = await expectDownloadAfter(page, async () => {
      await page.getByTestId("btn-podacha-build").click();
    });
    expect(fileName).toMatch(/\.zip$/i);
    await expect(page.getByTestId("podacha-modal")).toBeHidden({ timeout: 15_000 });

    await deleteCurrentCandidate(page);
  });

  test("scan link opens authenticated preview in new tab", async ({ page, context }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await candidateSectionNav(page).locator('[data-section-tab="documents"]').click();
    const panel = sectionPanel(detail, "documents");
    const scanDocType = `E2E-Scan-${Date.now()}`;
    await panel.getByPlaceholder("Тип документа").fill(scanDocType);
    await panel.getByRole("button", { name: "Добавить" }).click();
    const row = await customDocumentRowByType(panel, scanDocType);
    await uploadTinyPdfToDocumentRow(page, row, scanDocType);
    const rowAfterUpload = await customDocumentRowByType(panel, scanDocType);
    const link = rowAfterUpload.getByTestId("scan-download-link");
    await expect(link).toBeVisible({ timeout: 20_000 });

    const downloadRespPromise = page.waitForResponse(
      (res) => res.url().includes("/attachments/") && res.url().includes("/download") && res.status() === 200,
      { timeout: 30_000 }
    );
    const popupPromise = context.waitForEvent("page", { timeout: 30_000 }).catch(() => null);
    await link.click();
    const downloadResp = await downloadRespPromise;
    expect(downloadResp.ok()).toBeTruthy();
    const popup = await popupPromise;
    if (popup) {
      const bodyText = await popup.locator("body").innerText().catch(() => "");
      expect(bodyText).not.toContain("Authentication required");
      await popup.close();
    }

    await deleteCurrentCandidate(page);
  });

  test("generate documents: select template and download", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await candidateSectionNav(page).getByRole("button", { name: "Персональные данные" }).click();
    await detail.getByLabel("Фамилия").fill(`E2E-Gen-${Date.now()}`);
    await detail.getByRole("button", { name: "Сохранить профиль" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });

    await page.getByTestId("btn-generate-documents").click();
    await expect(page.getByRole("heading", { name: "Выберите шаблоны для генерации" })).toBeVisible();
    await expect(page.getByText("Загрузка шаблонов...")).toBeHidden({ timeout: 30_000 });

    const checkboxes = page.locator(".templates-select-item input[type='checkbox']");
    const count = await checkboxes.count();
    if (count === 0) {
      test.skip(true, "No templates in manager");
      return;
    }
    await checkboxes.first().check();

    const { fileName } = await expectDownloadAfter(page, async () => {
      await page.getByRole("button", { name: /Сгенерировать выбранные/ }).click();
    });
    expect(fileName.length).toBeGreaterThan(3);
    await expect(page.getByRole("heading", { name: "Выберите шаблоны для генерации" })).toBeHidden({
      timeout: 15_000,
    });

    await deleteCurrentCandidate(page);
  });

  test("Ukrainian contract: save field and persist after reopen", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    const marker = `E2E-Ukr-${Date.now()}`;
    await page.getByTestId("btn-ukr-contract").click();
    const modal = page.getByTestId("ukr-contract-modal");
    await expect(modal).toBeVisible();
    await modal.locator(".ukr-contract-grid label").first().locator("input").fill(marker);
    await modal.getByRole("button", { name: "Зберегти" }).click();
    await expect(modal.getByRole("button", { name: "Збереження…" })).toBeHidden({ timeout: 15_000 });
    await expect(modal).toBeHidden({ timeout: 10_000 });

    await page.getByTestId("btn-ukr-contract").click();
    await expect(modal).toBeVisible();
    await expect(modal.locator(".ukr-contract-grid label").first().locator("input")).toHaveValue(marker, {
      timeout: 15_000,
    });
    await modal.getByRole("button", { name: "Закрити" }).click();
    await expect(modal).toBeHidden();

    await deleteCurrentCandidate(page);
  });
});
