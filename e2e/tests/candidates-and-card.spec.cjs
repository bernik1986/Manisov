/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  waitForCandidateListReady,
  startEmptyCandidateDetail,
  deleteCurrentCandidate,
  candidateSectionNav,
  onNextDialog,
  customDocumentRow,
} = require("../helpers.cjs");

test.describe("Seamens list: filters and table", () => {
  test("list loads and shows range or empty row", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    const emptyRow = page.getByRole("cell", { name: "Кандидаты не найдены" });
    const hasRows = (await page.getByRole("button", { name: "Открыть карточку" }).count()) > 0;
    if (hasRows) {
      await expect(page.getByText(/Показано \d+–\d+ из \d+/)).toBeVisible();
    } else {
      await expect(emptyRow).toBeVisible();
    }
  });

  test("position filter is reflected in URL", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    await page.getByLabel("Фильтр по должности").selectOption("Master");
    await expect(page).toHaveURL(/position=Master/);
  });

  test("list position column uses recruitment Position Applied For", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    const idMatch = page.url().match(/\/candidates\/(\d+)/);
    expect(idMatch).toBeTruthy();
    const candidateId = idMatch[1];
    const stamp = Date.now();
    const surname = `E2EPos${stamp}`;

    await candidateSectionNav(page).getByRole("button", { name: "Персональные данные" }).click();
    await detail.getByLabel("Фамилия").fill(surname);
    await detail.getByRole("textbox", { name: "Имя", exact: true }).fill("List");
    await detail.getByRole("button", { name: "Сохранить профиль" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });

    await candidateSectionNav(page).locator('[data-section-tab="recruitment"]').click();
    await detail.getByLabel("Position Applied For").fill("2/E");
    await detail.getByRole("button", { name: /Сохранить заявку/i }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });

    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    await page.getByLabel("Поиск по фамилии").fill(surname);
    await expect(page.getByRole("cell", { name: "Second Engineer" }).first()).toBeVisible({
      timeout: 15_000,
    });

    await page.getByLabel("Фильтр по должности").selectOption("Second Engineer");
    await expect(page.getByRole("cell", { name: surname }).first()).toBeVisible({ timeout: 30_000 });

    await page.goto(`/candidates/${candidateId}`);
    await expect(page.getByTestId("candidate-detail")).toBeVisible();
    await deleteCurrentCandidate(page);
  });

  test("fleet filter is reflected in URL", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    await page.getByLabel("Фильтр по флоту").selectOption("Bulk Carrier");
    await expect(page).toHaveURL(/fleet=Bulk(\+|%20)Carrier/);
  });

  test("search query syncs to URL after debounce", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    await page.getByLabel("Поиск по фамилии").fill("NonexistentSurnameE2E");
    await expect(page).toHaveURL(/[?&]q=NonexistentSurnameE2E/, { timeout: 8_000 });
  });

  test("pagination: next page when available", async ({ page }, testInfo) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    const next = page.getByLabel("Следующая страница");
    if ((await next.count()) === 0) {
      testInfo.skip(true, "Pagination hidden when total_pages <= 1");
      return;
    }
    if (!(await next.isEnabled())) {
      testInfo.skip(true, "Need more than 20 candidates to test page 2");
      return;
    }
    await next.click();
    await expect(page).toHaveURL(/page=2/);
  });
});

test.describe("Candidate card: create, generate modal, focus param, delete", () => {
  test("new empty card → detail → generate modal → close → delete", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);

    await page.getByTestId("btn-new-empty-candidate").click();
    await expect(page).toHaveURL(/\/candidates\/\d+$/);
    await expect(page.getByTestId("candidate-detail")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Профиль кандидата / основная карточка" })).toBeVisible();

    await page.getByRole("button", { name: "Сгенерировать документы" }).click();
    await expect(page.getByRole("heading", { name: "Выберите шаблоны для генерации" })).toBeVisible();
    await page.getByRole("button", { name: "Закрыть" }).click();
    await expect(page.getByRole("heading", { name: "Выберите шаблоны для генерации" })).toBeHidden();

    const idMatch = page.url().match(/\/candidates\/(\d+)$/);
    const id = idMatch ? idMatch[1] : null;
    expect(id).toBeTruthy();
    await page.goto(`/candidates/${id}?focus=document:1`);
    await expect(page.getByTestId("candidate-detail")).toBeVisible();

    onNextDialog(page, { messageContains: "Удалить кандидата и все связанные данные" });
    await page.getByRole("button", { name: "Удалить кандидата" }).click();
    await expect(page).toHaveURL(/\/candidates/);
  });

  test("open first row card when list non-empty", async ({ page }, testInfo) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    if ((await page.getByRole("button", { name: "Открыть карточку" }).count()) === 0) {
      testInfo.skip(true, "No candidate rows in database");
      return;
    }
    const openBtn = page.getByRole("button", { name: "Открыть карточку" }).first();
    await openBtn.click();
    await expect(page).toHaveURL(/\/candidates\/\d+$/);
    await expect(page.getByTestId("candidate-detail")).toBeVisible();
  });

  test("admin: Documents tab — add new row (inline form)", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    await expect(detail).toBeVisible();

    await page.getByTestId("candidate-section-nav").locator('[data-section-tab="documents"]').click();
    const label = `E2E-Document-${Date.now()}`;
    await detail.getByPlaceholder("Тип документа").fill(label);
    await detail.getByRole("button", { name: "Добавить" }).first().click();
    const panel = detail.locator('[data-section-panel="documents"]');
    await expect(customDocumentRow(panel)).toBeVisible({ timeout: 15_000 });
  });
});
