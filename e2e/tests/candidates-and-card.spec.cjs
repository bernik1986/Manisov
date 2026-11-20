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

  test("pagination: next page when available", async ({ page }) => {
    const { API_BASE, getAuthToken, apiDeleteCandidate, uniqueUser } = require("../helpers.cjs");
    test.setTimeout(120_000);
    page.setDefaultTimeout(15_000);
    await loginAsAdmin(page);
    const headers = { Authorization: `Bearer ${await getAuthToken(page)}` };
    const prefix = uniqueUser("E2EPAGE").replace(/_/g, "").toUpperCase();
    const candidateIds = [];
    const surnames = [];
    try {
      for (let index = 1; index <= 21; index += 1) {
        const created = await page.request.post(`${API_BASE}/candidates`, { headers });
        expect(created.ok(), await created.text()).toBeTruthy();
        const { candidate_id: id } = await created.json();
        expect(id).toBeTruthy();
        candidateIds.push(id);
        const surname = `${prefix}${String(index).padStart(2, "0")}`;
        const updated = await page.request.put(`${API_BASE}/candidates/${id}`, {
          headers,
          data: { surname, first_name: "PAGINATION" },
        });
        expect(updated.ok(), await updated.text()).toBeTruthy();
        surnames.unshift(surname);
      }

      await page.goto(`/candidates?q=${encodeURIComponent(prefix)}`);
      await waitForCandidateListReady(page);
      const section = page.getByTestId("candidate-list-section");
      const rows = section.locator("tbody tr");
      const names = rows.locator("td:first-child");
      const next = page.getByLabel("Следующая страница");
      const previous = page.getByLabel("Предыдущая страница");
      await expect(section.locator(".candidate-list-range")).toHaveText("Показано 1–20 из 21");
      await expect(rows).toHaveCount(20);
      await expect(names).toHaveText(surnames.slice(0, 20));
      await expect(previous).toBeDisabled();
      await expect(next).toBeEnabled();
      await next.click();
      await expect(page).toHaveURL(/[?&]page=2(?:&|$)/);
      expect(new URL(page.url()).searchParams.get("q")).toBe(prefix);
      await expect(section.locator(".candidate-list-range")).toHaveText("Показано 21–21 из 21");
      await expect(rows).toHaveCount(1);
      await expect(names).toHaveText(surnames.slice(20));
      await expect(next).toBeDisabled();
      await expect(previous).toBeEnabled();
      await previous.click();
      await expect(names).toHaveText(surnames.slice(0, 20));
      expect(new URL(page.url()).searchParams.get("page") || "1").toBe("1");
    } finally {
      const cleanupErrors = [];
      for (const id of candidateIds) {
        try {
          const deleted = await apiDeleteCandidate(page, id);
          expect(deleted.ok(), await deleted.text()).toBeTruthy();
        } catch (error) {
          cleanupErrors.push(`candidate ${id}: ${error.message}`);
        }
      }
      expect.soft(cleanupErrors, "Pagination fixture cleanup").toEqual([]);
      const remaining = await page.request.get(`${API_BASE}/candidates/paged`, {
        headers, params: { q: prefix },
      });
      expect(remaining.ok(), await remaining.text()).toBeTruthy();
      expect((await remaining.json()).total).toBe(0);
    }
  });
});

test.describe("Candidate card: create, generate modal, focus param, delete", () => {
  test("a late initial card response cannot erase a newly uploaded photo", async ({ page }) => {
    await loginAsAdmin(page);
    let requests = 0;
    let release;
    let delivered;
    const held = new Promise((resolve) => { release = resolve; });
    const completed = new Promise((resolve) => { delivered = resolve; });
    await page.route(/\/api\/candidates\/\d+$/, async (route) => {
      if (route.request().method() !== "GET" || ++requests !== 1) return route.continue();
      const response = await route.fetch();
      await held;
      await route.fulfill({ response });
      delivered();
    });
    try {
      const detail = await startEmptyCandidateDetail(page);
      expect(requests).toBeGreaterThan(1);
      const png = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR4nGP4z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==",
        "base64"
      );
      await detail.getByTestId("candidate-photo-upload").locator('input[type="file"]').setInputFiles({
        name: "candidate.png", mimeType: "image/png", buffer: png,
      });
      await expect(detail.getByAltText("Фото кандидата")).toBeVisible();
      release();
      await completed;
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await expect(detail.getByAltText("Фото кандидата")).toBeVisible();
      await deleteCurrentCandidate(page);
    } finally {
      release();
    }
  });

  test("candidate photo preview is available in Podacha", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    const png = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR4nGP4z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==",
      "base64"
    );

    await detail
      .getByTestId("candidate-photo-upload")
      .locator('input[type="file"]')
      .setInputFiles({ name: "candidate.png", mimeType: "image/png", buffer: png });
    await expect(detail.getByAltText("Фото кандидата")).toBeVisible({ timeout: 15_000 });

    await detail.getByTestId("btn-podacha").click();
    const modal = page.getByTestId("podacha-modal");
    const photoItem = modal.locator(".templates-select-item", { hasText: "Фото кандидата" });
    await expect(photoItem).toBeVisible();
    await expect(photoItem.locator('input[type="checkbox"]')).toBeEnabled();
    await photoItem.locator('input[type="checkbox"]').check();
    await modal.getByRole("button", { name: "Закрыть" }).click();

    await deleteCurrentCandidate(page);
  });

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
