/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { loginAsAdmin, startEmptyCandidateDetail, customDocumentRow } = require("../helpers.cjs");

function nav(page) {
  return page.getByTestId("candidate-section-nav");
}

async function leaveCandidateList(page) {
  await page.goBack();
  await expect(page).toHaveURL(/\/candidates/);
}

test.describe("Date fields (DD-MM-YYYY) — all candidate sections", () => {
  test("Profile: birth date invalid shows hint, valid saves", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="profile:Персональные данные"]').click();
    const panel = detail.locator('[data-section-panel="profile:Персональные данные"]');
    const dob = panel.getByLabel("Дата рождения");
    await dob.fill("32-13-2020");
    await expect(panel.getByText("Некорректная дата")).toBeVisible();
    await dob.fill("15-08-1990");
    await expect(panel.getByText("Некорректная дата")).toBeHidden();
    await detail.getByRole("button", { name: "Сохранить профиль" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await leaveCandidateList(page);
  });

  test("Profile medical tab: passport issue date invalid inline", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="profile:Медицинские и визовые summary поля"]').click();
    const panel = detail.locator('[data-section-panel="profile:Медицинские и визовые summary поля"]');
    const passportIssue = panel.getByLabel("Passport Issue Date");
    await passportIssue.fill("31-02-2024");
    await expect(panel.getByText("Некорректная дата")).toBeVisible();
    await passportIssue.fill("10-01-2020");
    await expect(panel.getByText("Некорректная дата")).toBeHidden();
    await leaveCandidateList(page);
  });

  test("Recruitment: invalid Date Applied blocks save, then valid saves", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="recruitment"]').click();
    const panel = detail.locator('[data-section-panel="recruitment"]');
    await panel.getByLabel("Date Applied").fill("32-12-2020");
    await panel.getByRole("button", { name: "Сохранить заявку" }).click();
    await expect(detail.locator("p.error")).toContainText("Некорректная", { timeout: 10_000 });
    await panel.getByLabel("Date Applied").fill("05-05-2024");
    await panel.getByRole("button", { name: "Сохранить заявку" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await leaveCandidateList(page);
  });

  test("Documents: inline form invalid expiry hint, then add row", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="documents"]').click();
    const panel = detail.locator('[data-section-panel="documents"]');
    const inline = panel.locator(".inline-form");
    const issue = inline.locator('input[placeholder="дд-мм-гггг"]').nth(0);
    const expiry = inline.locator('input[placeholder="дд-мм-гггг"]').nth(1);
    await expiry.fill("32-01-2030");
    await expect(inline.getByText("Некорректная дата")).toBeVisible();
    await expiry.fill("10-06-2030");
    await expect(inline.getByText("Некорректная дата")).toBeHidden();
    const docType = `E2E-DateDoc-${Date.now()}`;
    await panel.getByPlaceholder("Тип документа").fill(docType);
    await panel.getByRole("button", { name: "Добавить" }).click();
    await expect(customDocumentRow(panel)).toBeVisible({ timeout: 15_000 });
    await leaveCandidateList(page);
  });

  test("Certificates: edit canonical row with date fields", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="certificates"]').click();
    const panel = detail.locator('[data-section-panel="certificates"]');
    const row = panel.locator(".table-wrap table").first().locator("tbody tr").filter({ hasText: "Basic Safety" });
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByRole("button", { name: "Редактировать" }).click();
    const issued = row.locator("td").nth(4).locator('input[placeholder="дд-мм-гггг"]');
    await issued.fill("00-01-2020");
    await expect(panel.getByText("Некорректная дата")).toBeVisible();
    await issued.fill("15-03-2025");
    await expect(panel.getByText("Некорректная дата")).toBeHidden();
    await row.locator("td").nth(5).locator('input[placeholder="дд-мм-гггг"]').fill("15-03-2030");
    await row.getByRole("button", { name: "Сохранить" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await leaveCandidateList(page);
  });

  test("Sea service modal: invalid sign-on shows error on Добавить", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="sea_service"]').click();
    const modal = page.getByTestId("sea-service-modal");
    await expect(modal).toBeVisible();
    await modal.getByPlaceholder("Судно").fill("E2E-Date-Sea");
    await modal.getByPlaceholder("Должность").fill("AB");
    const signOn = modal.locator(".inline-form").locator('input[placeholder="дд-мм-гггг"]').first();
    await signOn.fill("31-02-2022");
    await modal.getByRole("button", { name: "Добавить" }).click();
    await expect(detail.locator("p.error")).toContainText("Некорректная", { timeout: 10_000 });
    await signOn.fill("01-01-2022");
    await modal.getByRole("button", { name: "Добавить" }).click();
    await expect(modal.getByText("E2E-Date-Sea")).toBeVisible({ timeout: 15_000 });
    await modal.getByRole("button", { name: "Закрыть" }).click();
    await leaveCandidateList(page);
  });

  test("Flag documents: invalid issuance hint in inline form", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await nav(page).locator('[data-section-tab="flag_documents"]').click();
    const panel = detail.locator('[data-section-panel="flag_documents"]');
    const inline = panel.locator(".inline-form");
    const issuance = inline.getByPlaceholder("Выдача дд-мм-гггг");
    await issuance.fill("32-04-2025");
    await expect(inline.getByText("Некорректная дата")).toBeVisible();
    await issuance.fill("05-05-2025");
    await expect(inline.getByText("Некорректная дата")).toBeHidden();
    await leaveCandidateList(page);
  });

});
