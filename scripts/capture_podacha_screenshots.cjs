/* eslint-disable @typescript-eslint/no-var-requires */
/**
 * Capture UI screenshots for docs/PODACHA_INSTRUCTION_STAFF_RU.md
 * Run: node scripts/capture_podacha_screenshots.cjs
 * Requires frontend http://127.0.0.1:5173 and backend http://127.0.0.1:8000
 */
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const BASE = process.env.PW_BASE_URL || "http://127.0.0.1:5173";
const OUT_DIR = path.join(__dirname, "..", "docs", "screenshots", "podacha");
const ADMIN = { user: "admin", pass: "admin123" };

async function login(page) {
  await page.goto(`${BASE}/login`);
  await page.getByTestId("login-form").getByLabel("Логин").fill(ADMIN.user);
  await page.getByLabel("Пароль").fill(ADMIN.pass);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.waitForURL(/\/menu$/);
}

async function openFirstCandidate(page) {
  await page.goto(`${BASE}/candidates`);
  await page.getByText("Загрузка кандидатов...").waitFor({ state: "hidden", timeout: 30_000 }).catch(() => {});
  const openBtn = page.getByRole("button", { name: "Открыть карточку" }).first();
  if (await openBtn.isVisible().catch(() => false)) {
    await openBtn.click();
    await page.waitForURL(/\/candidates\/\d+$/);
    return;
  }
  await page.getByTestId("btn-new-empty-candidate").click();
  await page.waitForURL(/\/candidates\/\d+$/);
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "ru-RU",
  });
  const page = await context.newPage();

  try {
    await login(page);
    await page.screenshot({ path: path.join(OUT_DIR, "01-dashboard.png"), fullPage: false });

    await page.goto(`${BASE}/candidates`);
    await page.getByText("Загрузка кандидатов...").waitFor({ state: "hidden", timeout: 30_000 }).catch(() => {});
    await page.screenshot({ path: path.join(OUT_DIR, "02-candidates-list.png"), fullPage: false });

    await openFirstCandidate(page);
    await page.getByTestId("candidate-detail").waitFor({ state: "visible", timeout: 15_000 });
    const toolbar = page.locator(".candidate-admin-toolbar");
    await toolbar.waitFor({ state: "visible" });
    await toolbar.screenshot({ path: path.join(OUT_DIR, "03-toolbar-podacha.png") });

    await page.getByTestId("btn-podacha").click();
    const modal = page.getByTestId("podacha-modal");
    await modal.waitFor({ state: "visible", timeout: 15_000 });
    await page.getByText("Загрузка шаблонов…").waitFor({ state: "hidden", timeout: 30_000 }).catch(() => {});
    await modal.screenshot({ path: path.join(OUT_DIR, "04-podacha-modal.png") });

    const vesselSection = modal.locator(".podacha-section").first();
    if (await vesselSection.isVisible().catch(() => false)) {
      await vesselSection.screenshot({ path: path.join(OUT_DIR, "05-podacha-vessels.png") });
    }

    const templatesSection = modal.locator(".podacha-section").filter({ hasText: "Шаблоны" });
    if (await templatesSection.isVisible().catch(() => false)) {
      await templatesSection.screenshot({ path: path.join(OUT_DIR, "06-podacha-templates.png") });
    }

    const scansDoc = modal.locator(".podacha-section").filter({ hasText: "Сканы документов" });
    if (await scansDoc.isVisible().catch(() => false)) {
      await scansDoc.screenshot({ path: path.join(OUT_DIR, "07-podacha-scans-documents.png") });
    }

    const buildRow = modal.locator(".actions-row");
    if (await buildRow.isVisible().catch(() => false)) {
      await buildRow.screenshot({ path: path.join(OUT_DIR, "08-podacha-build-zip.png") });
    }

    console.log(`Screenshots saved to ${OUT_DIR}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
