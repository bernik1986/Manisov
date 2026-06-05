/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { loginAsAdmin } = require("../helpers.cjs");

const API_BASE = process.env.PW_API_BASE || "http://127.0.0.1:8000";

test("salary save updates contract tab salary preview", async ({ page }) => {
  await loginAsAdmin(page);

  const mgr = await page.request.get(`${API_BASE}/companies-manager`, {
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("authToken"))}` },
  });
  const companies = (await mgr.json()).companies || [];
  let companyId = null;
  let companyName = null;
  let rank = null;
  for (const c of companies) {
    const ranksResp = await page.request.get(
      `${API_BASE}/companies-manager/companies/${c.company_id}/salary-ranks`,
      { headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("authToken"))}` } }
    );
    const ranks = (await ranksResp.json()).ranks || [];
    if (ranks.length) {
      companyId = c.company_id;
      companyName = c.name;
      rank = ranks[0];
      break;
    }
  }
  test.skip(!companyId, "No company with salary ranks");

  const list = await page.request.get(`${API_BASE}/candidates?limit=1`, {
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("authToken"))}` },
  });
  const candidateId = (await list.json()).items[0].id;

  await page.goto(`/candidates/${candidateId}`);
  await page.getByTestId("candidate-section-nav").getByRole("button", { name: "Калькулятор зарплаты" }).click();
  await expect(page.getByTestId("salary-calculator-section")).toBeVisible();

  await page.getByTestId("salary-company-select").selectOption(String(companyId));
  await page.getByTestId("salary-rank-select").selectOption(rank);
  await page.getByTestId("salary-total-wage").fill("3000");
  await page.getByTestId("salary-btn-calculate").click();
  await expect(page.getByTestId("salary-owners-bonus")).not.toHaveValue("");
  await page.getByTestId("salary-btn-save").click();
  await expect(page.getByText("Расчёт сохранён")).toBeVisible({ timeout: 15_000 });

  await page.getByTestId("candidate-section-nav").getByRole("button", { name: "Контракт" }).click();
  await expect(page.getByTestId("contract-section")).toBeVisible();

  const companySelect = page.getByLabel("Компания");
  await companySelect.selectOption(String(companyId));
  await page.getByLabel("Должность").selectOption(rank);

  await expect(page.getByText("Сохраните расчёт в калькуляторе")).toHaveCount(0);
  await expect(page.getByText("Total Wage").locator("..")).toContainText("3000");
});
