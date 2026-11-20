const { test, expect } = require("@playwright/test");
const { API_BASE, getAuthToken, loginAs, loginAsAdmin, uniqueUser } = require("../helpers.cjs");

async function captureLayout(page, testInfo, name) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, animations: "disabled" });
  await testInfo.attach(name, { path, contentType: "image/png" });
}

test("a seafarer sends a scan and a recruiter approves it into the candidate record", async ({ page, browser }, testInfo) => {
  if (!process.env.PW_API_BASE) throw new Error("Run this test with the isolated E2E configuration");
  test.setTimeout(90_000);
  await loginAsAdmin(page);
  const username = uniqueUser("e2e_recognition");
  const password = "Intake-e2e-123";
  const adminToken = await getAuthToken(page);
  const registered = await page.request.post(`${API_BASE}/auth/register`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { username, password, role: "recruiter" },
  });
  expect(registered.ok(), await registered.text()).toBeTruthy();
  await page.getByRole("button", { name: "Выйти", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await loginAs(page, username, password);

  const recruiterToken = await getAuthToken(page);
  const headers = { Authorization: `Bearer ${recruiterToken}` };
  const created = await page.request.post(`${API_BASE}/candidates`, { headers });
  expect(created.ok(), await created.text()).toBeTruthy();
  const { candidate_id: id } = await created.json();
  await page.goto(`/candidates/${id}`);
  await page.getByRole("button", { name: "Скопировать ссылку для моряка" }).click();
  const link = page.getByLabel("Персональная ссылка для загрузки");
  await expect(link).toHaveValue(/\/upload-documents#[A-Za-z0-9_-]{43}$/);
  const url = await link.inputValue();

  const publicContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  try {
    const seafarer = await publicContext.newPage();
    await seafarer.setContent("<p>Synthetic scan for browser testing</p>");
    const scan = await seafarer.pdf();
    const catalog = seafarer.waitForRequest((request) => request.url().endsWith("/api/public/document-upload"));
    await seafarer.goto(url);
    const publicRequest = await catalog;
    const publicHeaders = await publicRequest.allHeaders();
    expect(publicHeaders["x-document-upload-token"]).toBe(new URL(url).hash.slice(1));
    expect(publicHeaders.authorization).toBeUndefined();
    expect(publicHeaders.cookie).toBeUndefined();
    await expect(seafarer.getByRole("heading", { name: "Загрузите документы" })).toBeVisible();
    const chooser = seafarer.waitForEvent("filechooser");
    await seafarer.getByRole("button", { name: "Прикрепить файлы" }).click();
    await (await chooser).setFiles({ name: "synthetic-scan.pdf", mimeType: "application/pdf", buffer: scan });
    await seafarer.getByRole("button", { name: "Проверить перед отправкой" }).click();
    await expect(seafarer.getByText("synthetic-scan.pdf")).toBeVisible();
    await captureLayout(seafarer, testInfo, "public-upload-mobile");
    await seafarer.getByRole("button", { name: "Отправить документы" }).click();
    await expect(seafarer.getByRole("heading", { name: "Документы отправлены" })).toBeVisible();

    await page.bringToFront();
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.getByRole("link", { name: "Новые документы 1" }).click({ timeout: 20_000 });
    const inbox = page.getByRole("region", { name: "Документы от моряков (1)" });
    await inbox.getByRole("link", { name: "Открыть карточку" }).click();
    await expect(page).toHaveURL(new RegExp(`/candidates/${id}\\?documentSubmission=[a-f0-9]{32}$`));
    const candidateInbox = page.getByTestId("candidate-document-inbox");
    await expect(candidateInbox.getByText("Присланы новые документы")).toBeVisible();
    await candidateInbox.getByRole("button", { name: "Распознать", exact: true }).click();
    const review = page.getByRole("dialog", { name: "Проверка сканов" });
    await expect(review.getByRole("img", { name: "synthetic-scan.pdf" })).toBeVisible({ timeout: 30_000 });
    await review.getByLabel("Тип документа").selectOption("document:SB", { timeout: 10_000 });
    await review.getByLabel("Номер", { exact: true }).fill("E2E-SB-4242");
    await captureLayout(page, testInfo, "recruiter-review-desktop");
    await review.getByRole("checkbox", { name: "Отметить synthetic-scan.pdf" }).check();
    await review.getByRole("button", { name: "Сохранить выбранные (1)" }).click();
    await expect(review.getByText("Сохранено документов: 1. Временные файлы удалены.")).toBeVisible();
    await review.getByRole("button", { name: "Закрыть проверку" }).click();
    await expect(candidateInbox).toHaveCount(0);

    const candidate = await page.request.get(`${API_BASE}/candidates/${id}`, { headers });
    expect(candidate.ok(), await candidate.text()).toBeTruthy();
    const { documents, attachments } = await candidate.json();
    const record = documents.find((doc) => doc.document_number === "E2E-SB-4242");
    expect(record?.document_category).toBe("SB");
    const attachment = attachments.find((item) => item.description === `document:${record.document_id}`);
    expect(attachment?.attachment_id).toBeTruthy();

    await page.getByRole("button", { name: "Скопировать ссылку для моряка" }).click();
    await expect(link).toHaveValue(url);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Отключить ссылку" }).click();
    await expect(link).toHaveCount(0);
    await seafarer.reload();
    await expect(seafarer.getByRole("alert")).toContainText("Ссылка больше не действует");
    await expect(seafarer).toHaveURL(url);
  } finally {
    await publicContext.close();
  }
});
