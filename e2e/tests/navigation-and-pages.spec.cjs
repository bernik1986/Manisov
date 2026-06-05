/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { loginAsAdmin } = require("../helpers.cjs");

test.describe("Top-level navigation and dashboard", () => {
  test("main menu: seamens, templates, notifications from dashboard CTA", async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

    await page.getByRole("button", { name: "Open Data" }).click();
    await expect(page).toHaveURL(/\/candidates$/);
    await expect(page.getByRole("heading", { name: "Seamen Data Management" })).toBeVisible();

    await page.getByTestId("nav-menu").click();
    await expect(page).toHaveURL(/\/menu$/);
    await page.getByRole("button", { name: "Open Notifications" }).click();
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(page.getByTestId("notifications-content")).toBeVisible();
  });

  test("sidebar links reach all private routes (admin)", async ({ page }) => {
    await loginAsAdmin(page);

    await page.getByTestId("nav-menu").click();
    await expect(page).toHaveURL(/\/menu$/);

    await page.getByTestId("nav-seamens").click();
    await expect(page).toHaveURL(/\/candidates$/);

    await page.getByTestId("nav-templates").click();
    await expect(page).toHaveURL(/\/templates$/);
    await expect(page.getByRole("heading", { name: "Manager Templates" })).toBeVisible();
    await expect(page.getByTestId("templates-manager")).toBeVisible();

    await page.getByTestId("nav-companies").click();
    await expect(page).toHaveURL(/\/companies$/);
    await expect(page.getByRole("heading", { name: "Company & Vessels" })).toBeVisible();
    await expect(page.getByTestId("companies-manager")).toBeVisible();

    await page.getByTestId("nav-notifications").click();
    await expect(page).toHaveURL(/\/notifications$/);

    await page.getByTestId("nav-users").click();
    await expect(page).toHaveURL(/\/users$/);
    await expect(page.getByRole("heading", { name: "User Management" })).toBeVisible();

    await page.getByTestId("nav-logs").click();
    await expect(page).toHaveURL(/\/logs$/);
    await expect(page.getByRole("heading", { name: "Audit Logs" })).toBeVisible({ timeout: 15_000 });
  });

  test('top bar "В меню" from templates', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/templates");
    await page.getByRole("button", { name: "В меню" }).click();
    await expect(page).toHaveURL(/\/menu$/);
  });
});

test.describe("Unauthenticated access", () => {
  test("visiting protected route redirects to login", async ({ page }) => {
    await page.goto("/candidates");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByTestId("login-form")).toBeVisible();
  });
});
