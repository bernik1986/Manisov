/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  loginAs,
  uniqueUser,
  startEmptyCandidateDetail,
  candidateSectionNav,
  sectionPanel,
  customDocumentRow,
  apiDeleteCandidate,
  onNextDialog,
  waitForUsernameInUsersTable,
} = require("../helpers.cjs");

test.describe.configure({ mode: "serial" });

const recruiterPassword = "recruitE2E_99";
let recruiterUsername;

test("admin registers recruiter user", async ({ page }) => {
  recruiterUsername = uniqueUser("e2e_recruiter");
  await loginAsAdmin(page);
  await page.goto("/users");
  const form = page.getByTestId("user-register-form");
  await form.getByPlaceholder("Логин").fill(recruiterUsername);
  await form.getByPlaceholder("Пароль").fill(recruiterPassword);
  await form.getByPlaceholder("Полное имя").fill("E2E Recruiter");
  await form.locator("select").selectOption("recruiter");
  await form.getByRole("button", { name: "Создать пользователя" }).click();
  await waitForUsernameInUsersTable(page, recruiterUsername);
});

test("recruiter edits documents but cannot delete whole candidate", async ({ page, browser }) => {
  if (!recruiterUsername) {
    test.skip();
    return;
  }

  const ctx = await browser.newContext();
  const recruiterPage = await ctx.newPage();
  await loginAs(recruiterPage, recruiterUsername, recruiterPassword);

  const detail = await startEmptyCandidateDetail(recruiterPage);
  await expect(recruiterPage.getByRole("button", { name: "Удалить кандидата" })).toHaveCount(0);
  await expect(recruiterPage.getByTestId("btn-podacha")).toBeVisible();
  await expect(recruiterPage.getByTestId("btn-generate-documents")).toBeVisible();

  await candidateSectionNav(recruiterPage).locator('[data-section-tab="documents"]').click();
  const panel = sectionPanel(detail, "documents");
  const docType = `E2E-Rec-${Date.now()}`;
  await panel.getByPlaceholder("Тип документа").fill(docType);
  await panel.getByRole("button", { name: "Добавить" }).click();
  await expect(customDocumentRow(panel)).toBeVisible({ timeout: 15_000 });

  const match = recruiterPage.url().match(/\/candidates\/(\d+)/);
  const candidateId = match ? Number(match[1]) : null;

  await loginAsAdmin(page);
  if (candidateId) {
    await apiDeleteCandidate(page, candidateId);
  }
  await page.goto("/users");
  const row = page.getByRole("row").filter({ hasText: recruiterUsername });
  onNextDialog(page, { messageContains: "Удалить этого пользователя" });
  await row.getByRole("button", { name: "Удалить" }).click();
  await expect(page.getByRole("cell", { name: recruiterUsername, exact: true })).toHaveCount(0, {
    timeout: 15_000,
  });

  await ctx.close();
});
