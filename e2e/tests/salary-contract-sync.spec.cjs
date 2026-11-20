/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { API_BASE, loginAsAdmin, getAuthToken, uniqueUser } = require("../helpers.cjs");

for (const scenario of [
  { title: "salary save updates contract tab salary preview", initialPeriod: "", period: "6 months" },
  { title: "late salary preview preserves employment period edits", initialPeriod: "3 months", period: "6 months", holdPreview: true },
  { title: "late salary preview preserves a cleared employment period", initialPeriod: "3 months", period: "", holdPreview: true },
]) {
test(scenario.title, async ({ page }) => {
  test.setTimeout(120_000);
  page.setDefaultTimeout(15_000);
  await loginAsAdmin(page);
  const headers = { Authorization: `Bearer ${await getAuthToken(page)}` };
  const name = uniqueUser("E2ESALARY");
  const rank = "Master";
  const cleanupUrls = [];
  let releasePreview;
  const components = {
    basic_monthly_wage: 1200,
    monthly_overtime: 400,
    overtime_rate: 8,
    sepf: 50,
    imtf: 25,
    leave: 150,
    leave_sub: 75,
    various_extra_overtime: 100,
  };
  try {
    const folderResponse = await page.request.post(`${API_BASE}/companies-manager/folders`, {
      headers, data: { name },
    });
    expect(folderResponse.ok(), await folderResponse.text()).toBeTruthy();
    const { folder } = await folderResponse.json();
    expect(folder.folder_id).toBeTruthy();
    cleanupUrls.push(`${API_BASE}/companies-manager/folders/${folder.folder_id}`);
    const companyResponse = await page.request.post(`${API_BASE}/companies-manager/companies`, {
      headers, data: { name, folder_id: folder.folder_id },
    });
    expect(companyResponse.ok(), await companyResponse.text()).toBeTruthy();
    const { company } = await companyResponse.json();
    const companyId = company.company_id;
    expect(companyId).toBeTruthy();
    cleanupUrls.push(`${API_BASE}/companies-manager/companies/${companyId}`);
    const vesselResponse = await page.request.post(`${API_BASE}/companies-manager/vessels`, {
      headers, data: { name: `${name} Vessel`, company_id: companyId, imo: "1234567", flag: "Liberia" },
    });
    expect(vesselResponse.ok(), await vesselResponse.text()).toBeTruthy();
    const { vessel } = await vesselResponse.json();
    expect(vessel.vessel_id).toBeTruthy();
    cleanupUrls.push(`${API_BASE}/companies-manager/vessels/${vessel.vessel_id}`);
    const templateResponse = await page.request.post(`${API_BASE}/companies-manager/salary-templates`, {
      headers, data: { company_id: companyId, rank, ...components },
    });
    expect(templateResponse.ok(), await templateResponse.text()).toBeTruthy();
    const { template } = await templateResponse.json();
    expect(template.template_id).toBeTruthy();
    cleanupUrls.push(`${API_BASE}/companies-manager/salary-templates/${template.template_id}`);
    const ranksResponse = await page.request.get(
      `${API_BASE}/companies-manager/companies/${companyId}/salary-ranks`, { headers }
    );
    expect(ranksResponse.ok(), await ranksResponse.text()).toBeTruthy();
    expect((await ranksResponse.json()).ranks).toEqual([rank]);

    const created = await page.request.post(`${API_BASE}/candidates`, { headers });
    expect(created.ok(), await created.text()).toBeTruthy();
    const { candidate_id: candidateId } = await created.json();
    expect(candidateId).toBeTruthy();
    cleanupUrls.push(`${API_BASE}/candidates/${candidateId}`);
    await page.goto(`/candidates/${candidateId}`);
    await expect(page.getByTestId("candidate-detail")).toBeVisible();
    const nav = page.getByTestId("candidate-section-nav");
    await nav.getByRole("button", { name: "Контракт", exact: true }).click();
    const contract = page.getByTestId("contract-section");
    await expect(contract).toBeVisible();
    await contract.getByLabel("Компания", { exact: true }).selectOption(String(companyId));
    await contract.getByLabel("Судно", { exact: true }).selectOption(String(vessel.vessel_id));
    await contract.getByLabel("Должность", { exact: true }).selectOption(rank);
    await expect(contract.getByText("Сохраните расчёт в калькуляторе", { exact: false })).toBeVisible();
    await contract.getByRole("button", { name: "Сохранить контракт", exact: true }).click();
    await expect(contract.getByText("Контракт сохранён", { exact: true })).toBeVisible();

    await nav.getByRole("button", { name: "Калькулятор зарплаты", exact: true }).click();
    const calculator = page.getByTestId("salary-calculator-section");
    await expect(calculator).toBeVisible();
    await page.getByTestId("salary-company-select").selectOption(String(companyId));
    await page.getByTestId("salary-rank-select").selectOption(rank);
    await expect(page.getByTestId("salary-total-wage")).toBeEnabled();
    const period = page.getByTestId("salary-period");
    await period.fill(scenario.initialPeriod);
    let heldPreview;
    if (scenario.holdPreview) {
      const pending = new Promise((resolve) => { releasePreview = resolve; });
      await page.route(`**/api/candidates/${candidateId}/salary-calculator/preview`, async (route) => {
        const draft = route.request().postDataJSON();
        if (draft.total_wage !== 3000 || heldPreview) return route.continue();
        const response = await route.fetch();
        expect(response.ok(), await response.text()).toBeTruthy();
        heldPreview = { draft, calculation: (await response.json()).calculation };
        await pending;
        await route.fulfill({ response });
      });
    }
    await page.getByTestId("salary-total-wage").fill("3000");
    await period.fill(scenario.period);
    if (scenario.holdPreview) {
      await expect.poll(() => heldPreview).toBeTruthy();
      expect(heldPreview.draft.period_of_employment).toBe(scenario.initialPeriod);
      expect(heldPreview.calculation.period_of_employment).toBe(scenario.initialPeriod);
      await expect(period).toHaveValue(scenario.period);
      releasePreview();
      await expect(page.getByTestId("salary-btn-calculate")).toBeEnabled();
      await expect(page.getByTestId("salary-owners-bonus")).toHaveValue("1000");
      await expect(period).toHaveValue(scenario.period);
    }
    await page.getByTestId("salary-btn-calculate").click();
    await expect(period).toHaveValue(scenario.period);
    await expect(calculator.getByTestId("salary-calculator-errors")).toHaveCount(0);
    await expect(calculator.getByLabel("Basic Monthly Wage", { exact: true })).toHaveValue("1200");
    await expect(calculator.getByLabel("Overtime Rate", { exact: true })).toHaveValue("8");
    // Overtime rate is display-only; the seven fixed components total 2000.
    await expect(calculator.getByLabel("Fixed Components Total", { exact: true })).toHaveValue("2000");
    await expect(page.getByTestId("salary-owners-bonus")).toHaveValue("1000");
    await page.getByTestId("salary-btn-save").click();
    await expect(calculator.getByText("Расчёт сохранён", { exact: false })).toBeVisible();

    await nav.getByRole("button", { name: "Контракт", exact: true }).click();
    await expect(contract).toBeVisible();
    await expect(contract.getByLabel("Компания", { exact: true })).toHaveValue(String(companyId));
    await expect(contract.getByLabel("Судно", { exact: true })).toHaveValue(String(vessel.vessel_id));
    await expect(contract.getByLabel("Должность", { exact: true })).toHaveValue(rank);
    await expect(contract.getByText("Сохраните расчёт в калькуляторе", { exact: false })).toHaveCount(0);
    const totalWage = contract.locator(".contract-preview-row").filter({
      has: page.getByText("Total Wage", { exact: true }),
    }).locator("dd");
    await expect(totalWage).toHaveText("3000");
    await expect(contract.locator("dd").filter({ hasText: /^1234567$/ })).toHaveCount(1);

    const contextResponse = await page.request.get(`${API_BASE}/candidates/${candidateId}/contract-context`, { headers });
    expect(contextResponse.ok(), await contextResponse.text()).toBeTruthy();
    expect(await contextResponse.json()).toMatchObject({
      salary_matches_selection: true,
      ranks_for_saved_company: [rank],
      contract: { company_id: companyId, vessel_id: vessel.vessel_id, rank },
      vessel: { vessel_id: vessel.vessel_id, company_id: companyId, name: `${name} Vessel`, imo: "1234567" },
      salary: {
        company_id: companyId, company_name: name, rank, total_wage: 3000,
        period_of_employment: scenario.period, fixed_components_total: 2000, owners_bonus: 1000,
        ...components,
      },
    });
    await page.reload();
    await nav.getByRole("button", { name: "Контракт", exact: true }).click();
    await expect(totalWage).toHaveText("3000");
    await expect(contract.getByLabel("Судно", { exact: true })).toHaveValue(String(vessel.vessel_id));
    await nav.getByRole("button", { name: "Калькулятор зарплаты", exact: true }).click();
    await expect(period).toHaveValue(scenario.period);
  } finally {
    releasePreview?.();
    await page.unrouteAll({ behavior: "wait" });
    const cleanupErrors = [];
    for (const url of cleanupUrls.reverse()) {
      try {
        const deleted = await page.request.delete(url, { headers });
        expect(deleted.ok(), await deleted.text()).toBeTruthy();
      } catch (error) {
        cleanupErrors.push(`${url}: ${error.message}`);
      }
    }
    expect.soft(cleanupErrors, "Salary fixture cleanup").toEqual([]);
  }
});
}
