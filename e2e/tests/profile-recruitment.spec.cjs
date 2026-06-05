/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  startEmptyCandidateDetail,
  deleteCurrentCandidate,
  candidateSectionNav,
  sectionPanel,
} = require("../helpers.cjs");

test.describe("Profile and recruitment fields", () => {
  test("profile: multiple fields save; recruitment position applied", async ({ page }) => {
    await loginAsAdmin(page);
    const detail = await startEmptyCandidateDetail(page);
    const stamp = Date.now();

    await candidateSectionNav(page).getByRole("button", { name: "Персональные данные" }).click();
    await detail.getByLabel("Фамилия").fill(`E2E-Sur-${stamp}`);
    await detail.getByRole("textbox", { name: "Имя", exact: true }).fill("Ivan");
    await detail.getByRole("textbox", { name: "Email", exact: true }).fill(`e2e_${stamp}@test.local`);
    await detail.getByRole("button", { name: "Сохранить профиль" }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });

    await candidateSectionNav(page).locator('[data-section-tab="recruitment"]').click();
    const panel = sectionPanel(detail, "recruitment");
    const position = `Chief Officer E2E ${stamp}`;
    await panel.getByLabel("Position Applied For").fill(position);
    await panel.getByRole("button", { name: /Сохранить заявку|Save/i }).click();
    await expect(detail.locator("p.error")).toBeHidden({ timeout: 15_000 });
    await expect(panel.getByLabel("Position Applied For")).toHaveValue(position, { timeout: 15_000 });

    await deleteCurrentCandidate(page);
  });
});
