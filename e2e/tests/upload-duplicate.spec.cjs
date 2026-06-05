/* eslint-disable @typescript-eslint/no-var-requires */
const fs = require("fs");
const { test, expect } = require("@playwright/test");
const {
  loginAsAdmin,
  apiDeleteCandidate,
  apiDeleteCandidatesBySurname,
  collectUploadResponses,
  repoFilePath,
  waitForCandidateListReady,
} = require("../helpers.cjs");

const SAMPLE_DOCX = repoFilePath(
  "tests",
  "2E Budurin CR-RT 05A _ SEAMEN'S APPLICATION _ INTERVIEW RECORD.docx"
);

test.describe("Application upload and duplicate merge", () => {
  test("upload DOCX creates candidate; re-upload prompts merge", async ({ page }) => {
    test.setTimeout(180_000);
    if (!fs.existsSync(SAMPLE_DOCX)) {
      test.skip(true, `Fixture missing: ${SAMPLE_DOCX}`);
      return;
    }

    page.on("dialog", async (dialog) => {
      const msg = dialog.message().toLowerCase();
      if (dialog.type() === "confirm" && msg.includes("открыть карточку")) {
        await dialog.dismiss();
        return;
      }
      await dialog.accept();
    });

    await loginAsAdmin(page);
    await apiDeleteCandidatesBySurname(page, "Budurin");
    await page.goto("/candidates");
    await waitForCandidateListReady(page);
    const form = page.getByTestId("form-application-upload");
    const fileInput = form.locator('input[type="file"]');

    await fileInput.setInputFiles(SAMPLE_DOCX);
    const firstBodies = await collectUploadResponses(page, () =>
      form.getByRole("button", { name: "Загрузить" }).click()
    );
    const created = firstBodies.find((body) => body.duplicate === false);
    expect(created).toBeTruthy();
    const candidateId = created.candidate_id;
    await expect(form.locator("p.success, p.warning")).toBeVisible({ timeout: 15_000 });

    await fileInput.setInputFiles(SAMPLE_DOCX);
    const secondBodies = await collectUploadResponses(
      page,
      () => form.getByRole("button", { name: "Загрузить" }).click(),
      {
        until: (bodies) =>
          bodies.some((body) => body.duplicate && body.requires_confirmation) &&
          bodies.some((body) => body.duplicate && body.updated),
      }
    );
    const dupPrompt = secondBodies.find((body) => body.duplicate && body.requires_confirmation);
    const merged = secondBodies.find((body) => body.duplicate && body.updated);
    expect(dupPrompt).toBeTruthy();
    expect(merged).toBeTruthy();
    expect(merged.candidate_id).toBe(candidateId);
    await expect(form.locator("p.warning")).toContainText(/обновл|уже есть|отменено/i, { timeout: 15_000 });

    await apiDeleteCandidate(page, candidateId);
    await apiDeleteCandidatesBySurname(page, "Budurin");
  });
});
