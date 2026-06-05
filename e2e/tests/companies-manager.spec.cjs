/* eslint-disable @typescript-eslint/no-var-requires */
const { test, expect } = require("@playwright/test");
const { loginAsAdmin, onNextDialog, selectManagerTreeRootIfNeeded } = require("../helpers.cjs");

function onNextPrompt(page, value) {
  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("prompt");
    await dialog.accept(value);
  });
}

test.describe("Companies manager", () => {
  test("create company and vessel, copy placeholder", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const companyName = `E2E Co ${Date.now()}`;
    const vesselName = `E2E Vessel ${Date.now()}`;

    await loginAsAdmin(page);
    await page.goto("/companies");
    await expect(page.getByTestId("companies-manager")).toBeVisible();
    await page.getByRole("button", { name: "Refresh" }).click();

    await selectManagerTreeRootIfNeeded(page, "Companies");
    onNextPrompt(page, companyName);
    await page.getByRole("button", { name: "+ Компания" }).click();
    await page.getByRole("button", { name: companyName }).click();

    await page.getByRole("button", { name: "+ Судно" }).click();
    await expect(page.getByTestId("vessel-form-modal")).toBeVisible();
    await page.getByLabel("Название").fill(vesselName);
    await page.getByLabel("IMO").fill("9876543");
    await page.getByLabel("Флаг").fill("Malta");
    await page.getByLabel("Тип судна").selectOption("Container Vessel");
    await page.getByRole("button", { name: "Добавить" }).click();

    await page.getByRole("cell", { name: vesselName }).click();
    await expect(page.getByTestId("vessel-detail")).toBeVisible();
    await page.getByTestId("copy-placeholder-imo").click();
    await expect(page.getByText("Скопировано")).toBeVisible({ timeout: 5000 });
  });
});
