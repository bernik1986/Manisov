/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { loginAsAdmin, uniqueUser, onNextDialog, waitForUsernameInUsersTable } = require("../helpers.cjs");

test.describe.configure({ mode: "serial" });

let viewerUsername;
const viewerPassword = "viewerE2E_99";

test("admin creates viewer user", async ({ page }) => {
  viewerUsername = uniqueUser("e2e_viewer");
  await loginAsAdmin(page);
  await page.goto("/users");
  await expect(page.getByRole("heading", { name: "User Management" })).toBeVisible();
  const form = page.getByTestId("user-register-form");
  await form.getByPlaceholder("Логин").fill(viewerUsername);
  await form.getByPlaceholder("Пароль").fill(viewerPassword);
  await form.getByPlaceholder("Полное имя").fill("E2E Viewer");
  await form.locator("select").selectOption("viewer");
  await form.getByRole("button", { name: "Создать пользователя" }).click();
  await waitForUsernameInUsersTable(page, viewerUsername);
});

test("viewer cannot see admin nav links; admin routes redirect to menu", async ({ browser }) => {
  if (!viewerUsername) {
    test.skip();
    return;
  }
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByTestId("login-form").getByLabel("Логин").fill(viewerUsername);
  await page.getByLabel("Пароль").fill(viewerPassword);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).toHaveURL(/\/menu$/);

  await expect(page.getByTestId("nav-users")).toHaveCount(0);
  await expect(page.getByTestId("nav-logs")).toHaveCount(0);
  await expect(page.getByTestId("nav-templates")).toBeVisible();
  await expect(page.getByTestId("nav-seamens")).toBeVisible();

  await page.goto("/users");
  await expect(page).toHaveURL(/\/menu$/);
  await page.goto("/logs");
  await expect(page).toHaveURL(/\/menu$/);

  await context.close();
});

test("admin can toggle viewer active status", async ({ page }) => {
  if (!viewerUsername) {
    test.skip();
    return;
  }
  await loginAsAdmin(page);
  await page.goto("/users");
  const row = page.getByRole("row").filter({ hasText: viewerUsername });
  const statusSelect = row.locator("td").nth(4).locator("select");

  await statusSelect.selectOption("inactive");
  await expect(statusSelect).toHaveValue("inactive");

  await statusSelect.selectOption("active");
  await expect(statusSelect).toHaveValue("active");
});

test("admin deletes e2e viewer user", async ({ page }) => {
  if (!viewerUsername) {
    test.skip();
    return;
  }
  await loginAsAdmin(page);
  await waitForUsernameInUsersTable(page, viewerUsername);
  const row = page.getByRole("row").filter({ hasText: viewerUsername });
  onNextDialog(page, { messageContains: "Удалить этого пользователя" });
  await row.getByRole("button", { name: "Удалить" }).click();
  await expect(page.getByRole("cell", { name: viewerUsername, exact: true })).toHaveCount(0);
});
