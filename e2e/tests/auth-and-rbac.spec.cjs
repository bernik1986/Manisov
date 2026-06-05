/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { ADMIN, loginAsAdmin } = require("../helpers.cjs");

test.describe("Auth and layout", () => {
  test("login shows dashboard", async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByTestId("crm-layout")).toBeVisible();
  });

  test("navigate to seamen list", async ({ page }) => {
    await loginAsAdmin(page);
    await page.getByRole("link", { name: "Seamens Data" }).click();
    await expect(page).toHaveURL(/\/candidates$/);
    await expect(page.getByRole("heading", { name: "Seamen Data Management" })).toBeVisible();
  });
});

test.describe("Admin-only navigation (default user is admin)", () => {
  test("admin sees Users and Logs links", async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page.getByTestId("nav-users")).toBeVisible();
    await expect(page.getByTestId("nav-logs")).toBeVisible();
  });

  test("admin can open user management", async ({ page }) => {
    await loginAsAdmin(page);
    await page.getByTestId("nav-users").click();
    await expect(page).toHaveURL(/\/users$/);
    await expect(page.getByRole("heading", { name: "User Management" })).toBeVisible();
  });

  test("admin can open audit logs", async ({ page }) => {
    await loginAsAdmin(page);
    await page.getByTestId("nav-logs").click();
    await expect(page).toHaveURL(/\/logs$/);
    await expect(page.getByRole("heading", { name: "Audit Logs" })).toBeVisible({ timeout: 15_000 });
  });

  test("self admin role selector is disabled", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/users");
    const selfUserId = await page.evaluate(() => {
      const raw = window.localStorage.getItem("authUser");
      if (!raw) return null;
      try {
        return JSON.parse(raw)?.user_id ?? null;
      } catch {
        return null;
      }
    });
    expect(selfUserId).toBeTruthy();
    const row = page.getByRole("row").filter({
      has: page.getByRole("cell", { name: String(selfUserId), exact: true }),
    });
    const roleSelect = row.locator("td").nth(3).locator("select");
    await expect(roleSelect).toBeDisabled();
  });
});
