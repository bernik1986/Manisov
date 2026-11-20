const { test, expect } = require("@playwright/test");
const { copyFileSync, mkdirSync, writeFileSync } = require("node:fs");
const path = require("node:path");

const candidateId = 900001;
const routeRoot = `/api/candidates/${candidateId}/document-intake`;
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1QAAAAASUVORK5CYII=", "base64");
const book = { key: "document:SB", kind: "document", label: "Seaman's Book", fields: ["number", "expiry_date", "place", "holder_name"] };
const certificate = { key: "certificate:FPFF", kind: "certificate", label: "Fire Prevention", fields: ["number", "issue_date", "code", "holder_name"] };
const taxId = { key: "document:ID code", kind: "document", label: "Tax ID Code", fields: ["number", "holder_name"] };
const row = (id, name, type, fields, extra = {}) => ({
  file_id: id, name, type_key: type?.key, fields, content_type: "image/png", page_count: 1, warnings: [], ...extra,
});
const initial = [
  row("a", "book-1.png", book, { number: "SB-10" }, { group_key: "book" }),
  row("b", "book-2.png", book, { number: "SB-10" }, { group_key: "book" }),
  row("c", "fire.pdf", certificate, { number: "FP-20", code: "A-VI/1-2" }, { content_type: "application/pdf", page_count: 2 }),
  row("d", "unknown.png", null, {}, { warnings: ["unknown_type", "ambiguous_date:issue_date", "ocr_unavailable"] }),
  row("e", "wrong.png", certificate, { number: "FP-21", holder_name: "Other Person" }, { warnings: ["holder_mismatch"] }),
  row("f", "broken.pdf", null, {}, { error: "invalid_scan", content_type: undefined }),
];

async function setup(page, { role = "recruiter", enabled = true, uploadEnabled = true, items = [], failOnce = "", saveError = "invalid_date", extraMatches = 0, background = false, externalItems = [] } = {}) {
  if (process.env.PW_INTAKE_OFFLINE === "1") {
    const dist = path.resolve(__dirname, process.env.PW_INTAKE_DIST || "../dist");
    await page.route("**/*", route => {
      const { pathname, origin } = new URL(route.request().url());
      if (origin !== new URL(test.info().project.use.baseURL).origin) return route.abort();
      if (pathname.startsWith("/assets/")) return route.fulfill({ path: path.join(dist, pathname) });
      if (pathname.startsWith("/api/")) return route.fallback();
      return route.fulfill({ path: path.join(dist, "index.html") });
    });
  }
  const state = { uploads: [], previews: [], saves: [], retries: 0, retryDone: false, discards: 0, reads: 0, calls: 0, statusChecks: 0, enabled, uploadEnabled, processed: 0, starts: 0 };
  const submissionId = "1".repeat(32);
  const token = "example-upload-token";
  let submissionStatus = externalItems.length ? "received" : "";
  const submissions = () => submissionStatus ? [{
    submission_id: submissionId, file_count: externalItems.length, status: submissionStatus,
    can_review: true, candidate_id: candidateId, candidate_name: "Taylor Sample",
  }] : [];
  const existing = [
    { id: 12, type_key: book.key, label: book.label, version: "a".repeat(64),
      fields: { number: "SB 10", expiry_date: "2030-01-01", place: "London" } },
    { id: 13, type_key: taxId.key, label: taxId.label, fields: { number: "123" } },
    ...Array.from({ length: extraMatches }, (_, index) => ({
      id: 100 + index, type_key: book.key, label: book.label, fields: { number: `HISTORY-${index}` },
    })),
  ];
  let batches = items.length ? [{ batch_id: "batch", items }] : [];
  await page.addInitScript((role) => {
    const payload = btoa(JSON.stringify({ sid: "intake-test-session", exp: Math.floor(Date.now() / 1000) + 3600 }));
    localStorage.setItem("authToken", `test.${payload}.test`);
    localStorage.setItem("authUser", JSON.stringify({ role, username: "intake-test", user_id: 1 }));
  }, role);
  await page.route("**/api/**", async route => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;
    if (pathname === `/api/candidates/${candidateId}`) {
      state.reads++;
      return route.fulfill({ json: { candidate: { candidate_id: candidateId, surname: "Sample", first_name: "Taylor" } } });
    }
    if (pathname === `${routeRoot}/status`) {
      state.statusChecks++;
      return route.fulfill({ json: { enabled: state.enabled } });
    }
    if (pathname === "/api/document-upload/notifications") {
      return route.fulfill({ json: { enabled: state.enabled, items: submissions() } });
    }
    if (pathname.startsWith(routeRoot)) {
      state.calls++;
      expect(req.headers().authorization).toMatch(/^Bearer test\./);
      if (pathname === `${routeRoot}/submissions` && req.method() === "GET") {
        return route.fulfill({ json: { items: submissions(), upload_enabled: state.uploadEnabled } });
      }
      if (pathname === `${routeRoot}/upload-link` && req.method() === "POST") {
        if (!state.uploadEnabled) return route.fulfill({ status: 404, json: { detail: "upload_link_unavailable" } });
        return route.fulfill({ json: { token } });
      }
      if (pathname === `${routeRoot}/submissions/${submissionId}/recognize` && req.method() === "POST") {
        state.starts++;
        submissionStatus = "in_review";
        const batch = { batch_id: submissionId, external: true, items: externalItems };
        batches = [...batches, batch];
        return route.fulfill({ status: 202, json: batch });
      }
      if (pathname === routeRoot && req.method() === "GET") {
        const visible = batches.map(batch => state.retries && batch.batch_id === "batch" ? {
          ...batch, name: batch.items[0].name, processed: batch.items.length - Number(!state.retryDone), total: batch.items.length,
          items: state.retryDone ? batch.items.map(item => item.retryable ?
            row(item.file_id, item.name, certificate, { number: "FP-RETRIED" }) : item) : [],
        } : background && batch.batch_id === "uploaded" ? {
          ...batch, name: "book-1.png", processed: state.processed, total: initial.length,
          items: state.processed < initial.length ? [] : batch.items,
        } : batch);
        return route.fulfill({ json: { candidate_name: "Taylor Sample", batches: visible, existing, catalog: [book, certificate, taxId] } });
      }
      if (pathname === routeRoot && req.method() === "POST") {
        state.uploads.push(req.postData());
        const batch = { batch_id: "uploaded", items: initial };
        batches = [...batches, batch];
        return route.fulfill({ status: 202, json: background ? {
          batch_id: batch.batch_id, name: "book-1.png", processed: 0, total: initial.length, items: [],
        } : batch });
      }
      if (pathname.includes("/files/")) {
        state.previews.push({ file: pathname.split("/").at(-1), page: url.searchParams.get("page") });
        return route.fulfill({ contentType: "image/png", body: PNG });
      }
      if (pathname === `${routeRoot}/batch/retry` && req.method() === "POST") {
        state.retries++;
        return route.fulfill({ status: 202, json: {
          batch_id: "batch", name: items[0].name, processed: items.length - 1, total: items.length, items: [],
        } });
      }
      if (pathname.endsWith("/save")) {
        const payload = req.postDataJSON();
        state.saves.push(payload);
        const results = payload.documents.map(doc => {
          if (doc.file_ids.includes(failOnce)) {
            failOnce = "";
            return { file_ids: doc.file_ids, status: "error", error: saveError };
          }
          const saved = new Set(doc.file_ids);
          batches = batches.map(batch => ({
            ...batch, items: batch.items.map(item => saved.has(item.file_id) ? { file_id: item.file_id, name: item.name, saved: true } : item),
          }));
          return { file_ids: doc.file_ids, status: "saved" };
        });
        const finished = payload.finish_submission && results.every(result => result.status === "saved");
        if (finished) {
          batches = batches.filter(batch => batch.batch_id !== submissionId);
          submissionStatus = "";
        }
        return route.fulfill({ json: finished ? { results, submission_finished: true } : { results } });
      }
      if (req.method() === "DELETE") {
        state.discards++;
        return route.fulfill({ status: 204 });
      }
      throw new Error(`Unexpected intake request: ${req.method()} ${pathname}`);
    }
    return route.fulfill({ json: { items: [], companies: [], vessels: [] } });
  });
  await page.goto(`/candidates/${candidateId}`);
  await expect(page.getByTestId("candidate-detail")).toBeVisible();
  return state;
}

test("intake review restores edits in the same tab but requires fresh type confirmation", async ({ page }) => {
  const state = await setup(page, { items: [
    row("mismatch", "selected-type.png", certificate, { number: "RAW-NUMBER" }, { warnings: ["type_hint_mismatch"] }),
  ] });
  const open = page.getByRole("button", { name: "Прикрепить и распознать документы" });
  const review = page.getByRole("dialog");
  const number = review.getByLabel("Номер", { exact: true });
  const confirm = review.getByRole("checkbox", { name: /подтверждаю выбранный тип/ });
  const save = review.getByRole("button", { name: "Сохранить в CRM", exact: true });
  await open.click();
  await expect(review.getByText(/хранятся 7 дней/)).toBeVisible();
  await expect(review.getByText(/Распознавание предложило другой тип/)).toBeVisible();
  await expect(save).toBeDisabled();
  await number.fill("DRAFT-PII");
  await confirm.check();
  await review.getByRole("checkbox", { name: "Отметить selected-type.png" }).check();
  await expect(review.getByRole("button", { name: "Сохранить выбранные (0)" })).toBeDisabled();
  await expect(save).toBeEnabled();
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("DRAFT-PII");
  await page.reload();
  await open.click();
  await expect(number).toHaveValue("DRAFT-PII");
  await expect(confirm).not.toBeChecked();
  await expect(save).toBeDisabled();
  await confirm.check();
  await save.click();
  await expect.poll(() => state.saves.length).toBe(1);
  expect(state.saves[0].documents[0].confirm_type_mismatch).toBe(true);
  await expect.poll(() => page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain("DRAFT-PII");
});

test("expired same-tab review changes are discarded even if the server still has the scan", async ({ page }) => {
  await setup(page, { items: [initial[2]] });
  const open = page.getByRole("button", { name: "Прикрепить и распознать документы" });
  const number = page.getByRole("dialog").getByLabel("Номер", { exact: true });
  await open.click();
  await number.fill("EXPIRED-EDIT");
  await expect.poll(() => page.evaluate(() => JSON.stringify(sessionStorage))).toContain("EXPIRED-EDIT");
  await page.evaluate(() => {
    const key = Object.keys(sessionStorage).find(key => key.startsWith("parcer:intake-review:v1:"));
    const drafts = JSON.parse(sessionStorage.getItem(key));
    drafts.batch.expiresAt = Date.now() - 1;
    sessionStorage.setItem(key, JSON.stringify(drafts));
  });
  await page.reload();
  await open.click();
  await expect(number).toHaveValue("FP-20");
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain("EXPIRED-EDIT");
});

test("a different authenticated session clears same-tab review data", async ({ page }) => {
  await setup(page, { items: [initial[2]] });
  const open = page.getByRole("button", { name: "Прикрепить и распознать документы" });
  const number = page.getByRole("dialog").getByLabel("Номер", { exact: true });
  await open.click();
  await number.fill("PREVIOUS-SESSION");
  await expect.poll(() => page.evaluate(() => JSON.stringify(sessionStorage))).toContain("PREVIOUS-SESSION");
  await page.evaluate(() => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const payload = btoa(JSON.stringify({ sid: "next-session", exp }));
    localStorage.setItem("authToken", `test.${payload}.test`);
    window.dispatchEvent(new StorageEvent("storage", { key: "authToken" }));
  });
  await expect(page.getByRole("dialog")).toBeHidden();
  await open.click();
  await expect(number).toHaveValue("FP-20");
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain("PREVIOUS-SESSION");
});

test("review remains editable and warns when tab storage is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "sessionStorage", {
      get: () => { throw new DOMException("Storage is blocked", "SecurityError"); },
    });
  });
  await setup(page, { items: [initial[2]] });
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  const review = page.getByRole("dialog");
  await expect(review.getByRole("status").filter({ hasText: "Браузер не может сохранить правки проверки" })).toBeVisible();
  await review.getByLabel("Номер", { exact: true }).fill("IN-MEMORY");
  await expect(review.getByRole("button", { name: "Сохранить в CRM", exact: true })).toBeEnabled();
});

test("recognition timeout and unknown save outcome preserve originals and explain recovery", async ({ page }) => {
  const state = await setup(page, { items: [initial[2], row("timeout", "timeout.png", null, {}, {
    error: "recognition_timeout", retryable: true,
  })], failOnce: "c", saveError: "save_outcome_unknown" });
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  const review = page.getByRole("dialog");
  await expect(review.getByText("Время распознавания истекло. Оригинал не удалён. Можно повторить распознавание.")).toBeVisible();
  const save = review.getByRole("button", { name: "Сохранить в CRM", exact: true });
  await review.getByLabel("Номер", { exact: true }).fill("KEEP-FOR-RETRY");
  await save.click();
  await expect(review.getByRole("alert")).toContainText("Оригинал не удалён. Обновите черновики");
  await expect(save).toBeDisabled();
  await review.getByRole("button", { name: "Обновить черновики и совпадения" }).click();
  await expect(review.getByLabel("Номер", { exact: true })).toHaveValue("KEEP-FOR-RETRY");
  await save.click();
  await expect(review.getByText("Сохранено документов: 1.")).toBeVisible();
  expect(state.saves).toHaveLength(2);
});

test("a new submission opens the existing review and keeps unchecked files until confirmation", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const state = await setup(page, { externalItems: [initial[2], initial[3]] });
  const copy = page.getByRole("button", { name: "Скопировать ссылку для моряка" });
  await copy.click();
  await expect(page.getByLabel("Персональная ссылка для загрузки")).toHaveValue(/\/upload-documents#example-upload-token$/);
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toMatch(/\/upload-documents#example-upload-token$/);
  await copy.click();
  await expect(page.getByLabel("Персональная ссылка для загрузки")).toHaveValue(/\/upload-documents#example-upload-token$/);

  await page.getByRole("link", { name: "Новые документы 1" }).click();
  await expect(page.getByRole("heading", { name: "Документы от моряков (1)" })).toBeVisible();
  await page.getByRole("link", { name: "Открыть карточку" }).click();
  const inbox = page.getByTestId("candidate-document-inbox");
  await expect(inbox.getByText("Присланы новые документы")).toBeVisible();
  expect(state.starts).toBe(0);
  await inbox.getByRole("button", { name: "Распознать", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  await expect(review.getByRole("img", { name: "fire.pdf" })).toBeVisible();
  await review.getByLabel("Номер", { exact: true }).fill("FP-EDITED");
  await review.getByRole("checkbox", { name: "Отметить fire.pdf" }).check();
  const save = review.getByRole("button", { name: "Сохранить выбранные (1)" });
  page.once("dialog", dialog => dialog.dismiss());
  await save.click();
  expect(state.saves).toEqual([]);
  page.once("dialog", dialog => dialog.accept());
  await save.click();
  await expect(review.getByText("Сохранено документов: 1. Временные файлы удалены.")).toBeVisible();
  expect(state.saves[0]).toMatchObject({
    bulk: true, finish_submission: true,
    documents: [{ file_ids: ["c"], fields: { number: "FP-EDITED" } }],
  });
  expect(state.starts).toBe(1);
  expect(state.uploads).toEqual([]);
  await review.getByRole("button", { name: "Закрыть проверку" }).click();
  await expect(inbox).toHaveCount(0);
});

test("replacing a seafarer submission sends the selected record version and refreshes its scan", async ({ page }) => {
  const state = await setup(page, { externalItems: [
    row("replacement", "replacement-book.pdf", book, { number: "SB-10", expiry_date: "2035-04-03" },
      { content_type: "application/pdf", page_count: 2 }),
  ] });
  await page.route(`**/api/candidates/${candidateId}`, route => {
    state.reads++;
    const replaced = state.saves.length > 0;
    return route.fulfill({ json: {
      candidate: { candidate_id: candidateId, surname: "Sample", first_name: "Taylor" },
      documents: [{ document_id: 12, document_type: book.label, document_category: "SB", document_number: "SB-10",
        date_of_expiry: replaced ? "2035-04-03" : "2030-01-01", is_primary: true }],
      attachments: [{ attachment_id: replaced ? 202 : 101, source: "document", description: "document:12",
        file_name: `${replaced ? "NEW" : "OLD"} Sample SB.pdf`, file_type: "application/pdf" }],
    } });
  });
  await page.route("**/api/attachments/202/download", route => route.fulfill({ contentType: "image/png", body: PNG }));
  await page.reload();
  await page.getByTestId("candidate-section-nav").getByRole("button", { name: "Documents", exact: true }).click();
  const documentRow = page.locator('tr[data-scan-target="document:12"]');
  await expect(documentRow.getByTestId("scan-download-link")).toHaveAttribute("title", "OLD Sample SB.pdf");

  const beforeSaveReads = state.reads;
  await page.getByTestId("candidate-document-inbox").getByRole("button", { name: "Распознать", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  await expect(review.getByRole("img", { name: "replacement-book.pdf" })).toBeVisible();
  await expect(review.getByText("Совпали тип и номер.")).toBeVisible();
  await review.getByLabel("Действие в CRM").selectOption("update");
  await review.getByRole("button", { name: "Сохранить в CRM", exact: true }).click();
  await expect(review.getByText("Сохранено документов: 1.")).toBeVisible();
  expect(state.saves).toEqual([{ bulk: false, documents: [{
    file_ids: ["replacement"], type_key: book.key, action: "update", existing_id: 12,
    existing_version: "a".repeat(64), fields: { number: "SB-10", expiry_date: "2035-04-03" }, confirm_holder: false,
  }] }]);
  await expect.poll(() => state.reads).toBeGreaterThan(beforeSaveReads);
  await review.getByRole("button", { name: "Закрыть проверку" }).click();
  await expect(documentRow.getByTestId("scan-download-link")).toHaveAttribute("title", "NEW Sample SB.pdf");
  const download = page.waitForRequest(request => request.url().endsWith("/api/attachments/202/download"));
  await documentRow.getByTestId("scan-download-link").click();
  expect((await download).method()).toBe("GET");
});

test("pausing public links leaves manager intake and received submissions usable", async ({ page }) => {
  const state = await setup(page, { externalItems: [initial[2]] });
  const copy = page.getByRole("button", { name: "Скопировать ссылку для моряка" });
  await copy.click();
  const link = page.getByLabel("Персональная ссылка для загрузки");
  await expect(link).toHaveValue(/#example-upload-token$/);

  state.uploadEnabled = false;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(copy).toHaveCount(0);
  await expect(link).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Прикрепить и распознать документы" })).toBeVisible();

  const inbox = page.getByTestId("candidate-document-inbox");
  await expect(inbox.getByText("Присланы новые документы")).toBeVisible();
  await inbox.getByRole("button", { name: "Распознать", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  await expect(review.getByRole("img", { name: "fire.pdf" })).toBeVisible();
  expect(state.starts).toBe(1);
});

test("retry recognizes retained files without reuploading or discarding other edits", async ({ page }) => {
  const state = await setup(page, { items: [
    row("book", "book.png", book, { number: "QA-BOOK" }),
    row("failed", "retry.png", null, {}, { error: "recognition_failed", retryable: true }),
  ] });
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  const number = review.getByLabel("Номер", { exact: true });
  await number.fill("QA-UNSAVED-EDIT");
  await review.getByRole("button", { name: "Повторить распознавание" }).click();
  await expect(review.getByRole("progressbar")).toHaveAttribute("value", "1");
  state.retryDone = true;
  await expect(review.getByRole("progressbar")).toHaveCount(0);
  await expect(number).toHaveValue("QA-UNSAVED-EDIT");
  await review.getByRole("button", { name: /retry\.png/ }).click();
  await expect(number).toHaveValue("FP-RETRIED");
  expect(state.retries).toBe(1);
  expect(state.uploads).toEqual([]);
});

test("a viewer cannot open intake or request its data", async ({ page }) => {
  const state = await setup(page, { role: "viewer" });
  await expect(page.getByTestId("candidate-detail")).toContainText("SAMPLE TAYLOR");
  await expect(page.getByRole("button", { name: "Прикрепить и распознать документы" })).toHaveCount(0);
  expect(state.calls).toBe(0);
  expect(state.statusChecks).toBe(0);
});

test("the runtime switch hides and reveals intake without a rebuild or reload", async ({ page }) => {
  const state = await setup(page, { enabled: false });
  await expect.poll(() => state.statusChecks).toBeGreaterThan(0);
  const button = page.getByRole("button", { name: "Прикрепить и распознать документы" });
  await expect(button).toHaveCount(0);
  state.enabled = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(button).toBeVisible();
  await button.click();
  await expect(page.getByRole("dialog", { name: "Проверка сканов" })).toBeVisible();
  state.enabled = false;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(button).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "Проверка сканов" })).toHaveCount(0);
});

test("folder review supports PNG previews, grouping, match decisions, bulk exclusion and individual approval", async ({ page }, testInfo) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  const folder = testInfo.outputPath("fixture-scans");
  mkdirSync(folder, { recursive: true });
  writeFileSync(path.join(folder, "tiny-candidate.png"), PNG);
  copyFileSync(path.resolve(__dirname, "../../../e2e/fixtures/tiny-scan.pdf"), path.join(folder, "tiny-scan.pdf"));
  await expect(review.getByRole("button", { name: "Выбрать папку" })).toBeEnabled();
  await review.locator("input[webkitdirectory]").setInputFiles(folder);
  await expect(review.getByText("Скан повреждён или не читается.")).toBeVisible();
  expect(state.uploads[0]).toContain('name="files"; filename="tiny-candidate.png"');
  expect(state.uploads[0]).toContain('name="files"; filename="tiny-scan.pdf"');
  expect(state.saves).toEqual([]);
  await expect(review.getByRole("img", { name: "book-1.png" })).toBeVisible();
  await expect.poll(() => review.getByRole("img").evaluate(img => img.naturalWidth)).toBeGreaterThan(0);
  await expect(review.getByText("Совпали тип и номер.")).toBeVisible();
  await expect(review.getByLabel("Действие в CRM").locator("option[value=create]")).toHaveCount(0);
  await review.getByLabel("Номер", { exact: true }).fill("SB-11");
  await expect(review.getByLabel("Действие в CRM").locator("option[value=create]")).toHaveCount(1);
  await review.getByLabel("Номер", { exact: true }).fill("SB-10");
  page.once("dialog", dialog => dialog.accept());
  await review.getByRole("button", { name: "Разъединить файлы" }).click();
  await review.getByRole("checkbox", { name: "Отметить book-1.png" }).check();
  await review.getByRole("checkbox", { name: "Отметить book-2.png" }).check();
  await review.getByRole("button", { name: "Объединить отмеченные (2)" }).click();
  await review.getByRole("button", { name: "Переместить файл вниз" }).click();
  await expect(review.getByLabel("Файл для просмотра").locator("option").first()).toHaveText("1. book-2.png");
  await review.getByLabel("Действие в CRM").selectOption("update");
  await expect(review.getByText("London")).toBeVisible();
  await review.getByLabel("Действителен до", { exact: true }).fill("2031-02-03");
  await review.getByRole("checkbox", { name: "Отметить book-2.png" }).check();
  await review.getByRole("checkbox", { name: "Отметить wrong.png" }).check();
  await review.getByRole("button", { name: /wrong.png/ }).click();
  const single = review.getByRole("button", { name: "Сохранить в CRM" });
  await expect(single).toBeDisabled();
  await review.getByRole("checkbox", { name: /Я проверил\(а\) оригинал/ }).check();
  await expect(single).toBeEnabled();
  await review.getByRole("button", { name: "Сохранить выбранные (1)" }).click();
  await expect(review.getByText("Сохранено документов: 1.")).toBeVisible();
  await expect(single).toBeEnabled();
  expect(state.saves[0]).toEqual({ bulk: true, documents: [{
    file_ids: ["b", "a"], type_key: book.key, action: "update", existing_id: 12, existing_version: "a".repeat(64),
    fields: { number: "SB-10", expiry_date: "2031-02-03" }, confirm_holder: false,
  }] });
  await single.click();
  await expect(review.getByRole("button", { name: /wrong.png Сохранено в CRM/ })).toBeVisible();
  expect(state.saves[1].bulk).toBe(false);
  expect(state.saves[1].documents[0].confirm_holder).toBe(true);
  await review.getByRole("button", { name: /fire.pdf/ }).click();
  await expect(review.getByLabel("Код сертификата")).toHaveValue("A-VI/1-2");
  await expect(review.getByLabel("Место выдачи")).toHaveCount(0);
  await review.getByRole("button", { name: "Следующая страница" }).click();
  await expect(review.getByText("Страница 2 из 2")).toBeVisible();
  await expect(review.getByRole("img", { name: "fire.pdf" })).toBeVisible();
  expect(state.previews).toContainEqual({ file: "c", page: "2" });
  await review.getByRole("button", { name: /unknown.png/ }).click();
  await expect(review.getByText("Тип не распознан. Выберите его по оригиналу.")).toBeVisible();
  await expect(review.getByText("Локальное распознавание изображений недоступно.", { exact: false })).toBeVisible();
  await review.getByLabel("Тип документа").selectOption(taxId.key);
  await review.getByLabel("Номер", { exact: true }).fill("987");
  await review.getByLabel("Действие в CRM").selectOption("create");
  await expect(single).toBeEnabled();
  await review.getByRole("button", { name: "Закрыть проверку" }).click();
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  await expect(review.getByLabel("Номер", { exact: true })).toHaveValue("987");
  page.once("dialog", dialog => dialog.accept());
  await review.getByRole("button", { name: "Удалить черновик" }).click();
  await expect(review.getByText("Черновик удалён.")).toBeVisible();
  await expect(review.getByRole("button", { name: /unknown.png/ })).toHaveCount(0);
  expect(state.discards).toBe(1);
  expect(state.reads).toBeGreaterThanOrEqual(3);
});

test("background progress resumes after closing the dialog and reloading the page", async ({ page }) => {
  const state = await setup(page, { background: true });
  const entry = page.getByRole("button", { name: "Прикрепить и распознать документы" });
  await entry.click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  await expect(review.getByRole("button", { name: "Выбрать файлы" })).toBeEnabled();
  await review.locator("input[accept]").setInputFiles({ name: "book-1.png", mimeType: "image/png", buffer: PNG });
  await expect(review.getByText("Обработано 0 из 6 файлов")).toBeVisible();
  state.processed = 2;
  await expect(review.getByText("Обработано 2 из 6 файлов")).toBeVisible();
  await review.getByRole("button", { name: "Закрыть проверку" }).click();
  await expect(review).not.toBeVisible();
  state.processed = 4;
  await page.reload();
  await entry.click();
  await expect(review.getByText("Обработано 4 из 6 файлов")).toBeVisible();
  state.processed = 6;
  await expect(review.getByRole("progressbar")).toHaveCount(0);
  await expect(review.getByRole("img", { name: "book-1.png" })).toBeVisible();
  expect(state.uploads).toHaveLength(1);
});

test("Russian mobile: partial save retains the failed document and no upload leaves the app", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await setup(page, { failOnce: "c" });
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  await expect(review.getByRole("button", { name: "Выбрать файлы" })).toBeEnabled();
  await review.locator('input[type="file"]:not([webkitdirectory])').setInputFiles([
    { name: "unknown.png", mimeType: "image/png", buffer: PNG },
    { name: "fire.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n") },
  ]);
  await review.getByRole("button", { name: /unknown.png/ }).click();
  await review.getByRole("button", { name: "К полям", exact: true }).click();
  await expect(review.getByRole("heading", { name: "Поля CRM" })).toBeFocused();
  await expect(review.getByRole("heading", { name: "Поля CRM" })).toBeInViewport();
  await review.getByRole("button", { name: "К оригиналу", exact: true }).click();
  await expect(review.getByRole("heading", { name: "Оригинал" })).toBeFocused();
  await expect(review.getByRole("heading", { name: "Оригинал" })).toBeInViewport();
  await expect(review.getByText("Тип не распознан. Выберите его по оригиналу.")).toBeVisible();
  await review.getByLabel("Тип документа").selectOption(certificate.key);
  await expect(review.getByText("Дата выдачи: неоднозначная дата. Проверьте по оригиналу.")).toBeVisible();
  await review.getByLabel("Номер", { exact: true }).fill("FP-22");
  await review.getByRole("checkbox", { name: "Отметить unknown.png" }).check();
  await review.getByRole("checkbox", { name: "Отметить fire.pdf" }).check();
  await review.getByRole("button", { name: "Сохранить выбранные (2)" }).click();
  await expect(review.getByRole("alert")).toContainText("Проверьте формат даты.");
  await expect(review.getByRole("button", { name: /unknown.png Сохранено в CRM/ })).toBeVisible();
  await expect(review.getByLabel("Номер", { exact: true })).toHaveValue("FP-20");
  await review.getByRole("button", { name: "Сохранить в CRM", exact: true }).click();
  await expect(review.getByRole("button", { name: /fire.pdf Сохранено в CRM/ })).toBeVisible();
  expect(state.saves.map(call => call.documents.flatMap(doc => doc.file_ids))).toEqual([["c", "d"], ["c"]]);
  expect(await review.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
});

test("the original remains visible while scrolling a long review on a laptop", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 650 });
  await setup(page, { items: initial, extraMatches: 14 });
  await page.getByRole("button", { name: "Прикрепить и распознать документы" }).click();
  const review = page.getByRole("dialog", { name: "Проверка сканов" });
  const original = review.locator(".intake-original");
  const scan = review.getByRole("region", { name: "Оригинал" });
  const image = scan.getByRole("img", { name: "book-1.png" });
  await review.getByRole("button", { name: /book-1.png/ }).click();
  await expect(image).toBeInViewport({ ratio: 1 });
  const before = await original.boundingBox();
  const modal = await review.boundingBox();
  const scroll = await review.evaluate(el => el.scrollTop);
  await review.locator(".intake-editor").hover({ position: { x: 20, y: 190 } });
  await page.mouse.wheel(0, 240);
  await expect.poll(() => review.evaluate(el => el.scrollTop)).toBeGreaterThan(scroll + 150);
  const after = await original.boundingBox();
  expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(2);
  expect(after.y).toBeGreaterThanOrEqual(modal.y);
  expect(after.y + after.height).toBeLessThanOrEqual(modal.y + modal.height);
  await expect(image).toBeInViewport({ ratio: 1 });
  const fitted = await scan.boundingBox();
  await review.getByRole("button", { name: "Увеличить скан" }).click();
  await expect(scan).toHaveAttribute("tabindex", "0");
  expect(await scan.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  expect((await scan.boundingBox()).height).toBeCloseTo(fitted.height, 0);
  await review.getByRole("button", { name: "Вписать скан" }).click();
  await page.screenshot({ path: testInfo.outputPath("pinned-preview-laptop.png") });
});
