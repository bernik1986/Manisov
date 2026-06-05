/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { loginAsAdmin, ADMIN } = require("../helpers.cjs");

test.describe("Login edge cases and logout", () => {
  test("invalid credentials show error and stay on login", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-form").getByLabel("Логин").fill("no_such_user");
    await page.getByLabel("Пароль").fill("wrong");
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByText("Неверный логин или пароль")).toBeVisible();
  });

  test("logout clears session", async ({ page }) => {
    await loginAsAdmin(page);
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/menu");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("re-login after logout", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-form").getByLabel("Логин").fill(ADMIN.user);
    await page.getByLabel("Пароль").fill(ADMIN.pass);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).toHaveURL(/\/menu$/);
  });
});

test.describe("Upload forms: client validation without files", () => {
  test("application upload requires file", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await expect(page.getByText("Загрузка кандидатов...")).toBeHidden({ timeout: 30_000 });
    const form = page.getByTestId("form-application-upload");
    await form.getByRole("button", { name: "Загрузить" }).click();
    await expect(form.getByText("Выберите файл для загрузки")).toBeVisible();
  });

  test("CV upload block is not shown on candidates page", async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/candidates");
    await expect(page.getByText("Загрузка кандидатов...")).toBeHidden({ timeout: 30_000 });
    await expect(page.getByTestId("form-cv-upload")).toHaveCount(0);
    await expect(page.getByTestId("form-application-upload")).toBeVisible();
  });
});
