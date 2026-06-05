/* eslint-disable @typescript-eslint/no-var-requires */
const fs = require("fs");
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  expectDownloadAfter,
  repoFilePath,
  onNextDialog,
  selectTemplatesManagerRoot,
} = require("../helpers.cjs");

const TEMPLATE_DOCX = repoFilePath("templates", "CHANDRIS_APPLICATION.docx");

function onNextPrompt(page, value) {
  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("prompt");
    await dialog.accept(value);
  });
}

test.describe("Templates manager CRUD", () => {
  test("create subfolder, upload docx, download, delete file and folder", async ({ page }) => {
    if (!fs.existsSync(TEMPLATE_DOCX)) {
      test.skip(true, `Missing ${TEMPLATE_DOCX}`);
      return;
    }

    const folderName = `E2E_${Date.now()}`;

    await loginAsAdmin(page);
    await page.goto("/templates");
    await expect(page.getByTestId("templates-manager")).toBeVisible();
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByText("Загрузка...")).toBeHidden({ timeout: 30_000 });

    await selectTemplatesManagerRoot(page);
    onNextPrompt(page, folderName);
    await page.getByRole("button", { name: "+ Subfolder" }).click();
    await page.getByRole("button", { name: folderName }).click();
    await expect(page.getByRole("heading", { name: folderName })).toBeVisible({ timeout: 10_000 });

    await page.locator(".templates-dropzone").locator('input[type="file"]').first().setInputFiles(TEMPLATE_DOCX);
    await expect(page.getByText("CHANDRIS_APPLICATION.docx")).toBeVisible({ timeout: 30_000 });

    const row = page.locator("tbody tr").filter({ hasText: "CHANDRIS_APPLICATION.docx" });
    const { fileName } = await expectDownloadAfter(page, async () => {
      await row.getByRole("button", { name: "Скачать" }).click();
    });
    expect(fileName).toMatch(/\.docx$/i);

    onNextDialog(page, { messageContains: "Удалить файл" });
    await row.getByRole("button", { name: "Удалить" }).click();
    await expect(page.getByText("CHANDRIS_APPLICATION.docx")).toHaveCount(0, { timeout: 15_000 });

    onNextDialog(page, { messageContains: "Delete folder" });
    await page.getByRole("button", { name: "Delete folder" }).click();
    await expect(page.getByRole("button", { name: folderName })).toHaveCount(0, { timeout: 15_000 });
  });
});
