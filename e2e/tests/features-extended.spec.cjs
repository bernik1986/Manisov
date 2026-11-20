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
    const { execFileSync } = require("node:child_process");
    const fs = require("node:fs");
    const { API_BASE, getAuthToken, uniqueUser } = require("../helpers.cjs");
    page.setDefaultTimeout(15_000);
    await loginAsAdmin(page);
    const headers = { Authorization: `Bearer ${await getAuthToken(page)}` };
    const name = uniqueUser("E2EGEN").toUpperCase();
    const fileName = `${name}.docx`;
    const cleanupUrls = [];
    let downloadPath;
    try {
      const folderResponse = await page.request.post(`${API_BASE}/templates-manager/folders`, {
        headers, data: { name },
      });
      expect(folderResponse.ok(), await folderResponse.text()).toBeTruthy();
      const { folder } = await folderResponse.json();
      expect(folder.folder_id).toBeTruthy();
      cleanupUrls.push(`${API_BASE}/templates-manager/folders/${folder.folder_id}`);

      const template = execFileSync("python", ["-c", [
        "import sys",
        "from io import BytesIO",
        "from docx import Document",
        "doc = Document()",
        "doc.add_paragraph('Synthetic generator fixture: {{ surname }} / {{ first_name }}')",
        "output = BytesIO()",
        "doc.save(output)",
        "sys.stdout.buffer.write(output.getvalue())",
      ].join("\n")], { timeout: 30_000, windowsHide: true });
      const upload = await page.request.post(`${API_BASE}/templates-manager/files`, {
        headers,
        multipart: {
          folder_id: String(folder.folder_id),
          file: {
            name: fileName,
            mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer: template,
          },
        },
      });
      expect(upload.ok(), await upload.text()).toBeTruthy();
      const { file } = await upload.json();
      expect(file).toMatchObject({ file_name: fileName, folder_id: folder.folder_id });
      expect(file.template_file_id).toBeTruthy();

      const created = await page.request.post(`${API_BASE}/candidates`, { headers });
      expect(created.ok(), await created.text()).toBeTruthy();
      const { candidate_id: candidateId } = await created.json();
      expect(candidateId).toBeTruthy();
      cleanupUrls.push(`${API_BASE}/candidates/${candidateId}`);
      const updated = await page.request.put(`${API_BASE}/candidates/${candidateId}`, {
        headers, data: { surname: name, first_name: "SYNTHETIC" },
      });
      expect(updated.ok(), await updated.text()).toBeTruthy();
      await page.goto(`/candidates/${candidateId}`);
      await expect(page.getByTestId("candidate-detail")).toBeVisible();
      await page.getByTestId("btn-generate-documents").click();
      const heading = page.getByRole("heading", { name: "Выберите шаблоны для генерации" });
      await expect(heading).toBeVisible();
      await expect(page.getByText("Загрузка шаблонов...")).toBeHidden({ timeout: 30_000 });
      await page.locator(".templates-select-modal").getByRole("button", { name }).click();
      const templateItem = page.locator(".templates-select-item").filter({ hasText: fileName });
      await expect(templateItem).toHaveCount(1);
      await templateItem.getByRole("checkbox").check();
      await expect(templateItem.getByRole("checkbox")).toBeChecked();
      const generate = page.getByRole("button", { name: "Сгенерировать выбранные (1)", exact: true });
      await expect(generate).toBeEnabled();

      const downloaded = await expectDownloadAfter(page, () => generate.click());
      downloadPath = downloaded.savePath;
      expect(downloaded.fileName).toMatch(/\.docx$/i);
      expect(await downloaded.download.failure()).toBeNull();
      const renderedText = execFileSync("python", ["-c", [
        "import json, sys",
        "from docx import Document",
        "print(json.dumps([p.text for p in Document(sys.argv[1]).paragraphs]))",
      ].join("\n"), downloadPath], { encoding: "utf8", timeout: 30_000, windowsHide: true });
      expect(JSON.parse(renderedText)).toEqual([`Synthetic generator fixture: ${name} / SYNTHETIC`]);
      await expect(heading).toBeHidden({ timeout: 15_000 });
    } finally {
      const cleanupErrors = [];
      for (const url of cleanupUrls.reverse()) {
        try {
          const deleted = await page.request.delete(url, { headers });
          expect(deleted.ok(), await deleted.text()).toBeTruthy();
        } catch (error) {
          cleanupErrors.push(`${url}: ${error.message}`);
        }
      }
      if (downloadPath) fs.rmSync(downloadPath, { force: true });
      expect.soft(cleanupErrors, "Generator fixture cleanup").toEqual([]);
    }
  });

});
