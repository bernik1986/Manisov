/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  API_BASE,
  API_REQUEST_TIMEOUT,
  warmNotificationsApi,
  waitForNotificationsPageReady,
} = require("../helpers.cjs");

test.describe("Templates manager", () => {
  test("root folder and tools render", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/templates");
    await expect(page.getByTestId("templates-manager")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Templates$/ })).toBeVisible();
    await expect(page.getByPlaceholder("Поиск папок и файлов…")).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
    await expect(page.getByText(/Перетащите файлы/)).toBeVisible();
  });
});

test.describe("Notifications", () => {
  test.describe.configure({ timeout: 90_000 });
  test("page loads; empty or grouped list", async ({ page }) => {
    await loginAsAdmin(page);
    await waitForNotificationsPageReady(page);
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(page.getByTestId("notifications-content")).toBeVisible();
  });

  test("expired document notification opens focused document row", async ({ page }) => {
    await loginAsAdmin(page);
    const token = await page.evaluate(() => localStorage.getItem("authToken"));
    expect(token).toBeTruthy();

    const createResp = await page.request.post(`${API_BASE}/candidates`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: API_REQUEST_TIMEOUT,
    });
    expect(createResp.ok()).toBeTruthy();
    const { candidate_id: candidateId } = await createResp.json();
    expect(candidateId).toBeTruthy();

    const expiredDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const docType = `E2E-Doc-${Date.now()}`;
    const addDocResp = await page.request.post(`${API_BASE}/candidates/${candidateId}/documents`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: API_REQUEST_TIMEOUT,
      data: { document_type: docType, date_of_expiry: expiredDate },
    });
    expect(addDocResp.ok()).toBeTruthy();
    const { document } = await addDocResp.json();
    const docId = document?.document_id;
    expect(docId).toBeTruthy();

    await expect
      .poll(async () => {
        const syncResp = await page.request.get(`${API_BASE}/notifications`, {
          headers: { Authorization: `Bearer ${token}` },
          params: { sent: false, candidate_id: candidateId },
          timeout: API_REQUEST_TIMEOUT,
        });
        if (!syncResp.ok()) {
          return false;
        }
        const items = (await syncResp.json()).items || [];
        return items.some(
          (item) =>
            item.candidate_id === candidateId &&
            item.document_id === docId &&
            String(item.message || "").toLowerCase().includes("просрочен")
        );
      }, { timeout: 30_000 })
      .toBeTruthy();

    await waitForNotificationsPageReady(page);

    const candidateBlock = page
      .locator(".detail-block")
      .filter({ has: page.getByRole("heading", { name: new RegExp(`#${candidateId}\\b`) }) })
      .first();
    await expect(candidateBlock).toBeVisible({ timeout: 15_000 });

    const expandBtn = candidateBlock.getByRole("button", { name: /Раскрыть/ }).first();
    if (await expandBtn.isVisible().catch(() => false)) {
      await expandBtn.click();
    }

    const escapedDocType = docType.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const targetNotifBtn = candidateBlock
      .getByRole("button", { name: new RegExp(`Документ просрочен:\\s*${escapedDocType}\\.?`) })
      .first();
    await expect(targetNotifBtn).toBeVisible({ timeout: 15_000 });
    await targetNotifBtn.click();

    await expect(page).toHaveURL(new RegExp(`/candidates/${candidateId}\\?focus=document%3A${docId}`), {
      timeout: 15_000,
    });
    const targetRow = page.locator(`[data-scan-target="document:${docId}"]`);
    await expect(targetRow).toBeVisible({ timeout: 15_000 });
    await expect(targetRow).toHaveClass(/scan-target-highlight/);

    await page.request.delete(`${API_BASE}/candidates/${candidateId}`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: API_REQUEST_TIMEOUT,
    });
  });
});

test.describe("Audit logs", () => {
  test("filters and table", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/logs");
    await expect(page.getByRole("heading", { name: "Audit Logs" })).toBeVisible();
    await expect(page.getByText("Загрузка...")).toBeHidden({ timeout: 30_000 });
    await expect(page.getByRole("columnheader", { name: "Действие" })).toBeVisible();
    await page.getByRole("button", { name: "Применить" }).click();
    await expect(page.getByText("Загрузка...")).toBeHidden({ timeout: 30_000 });
  });
});
