/* eslint-disable @typescript-eslint/no-var-requires */
const { defineConfig, devices } = require("@playwright/test");
const path = require("path");

module.exports = defineConfig({
  testDir: path.join(__dirname, "e2e", "tests"),
  timeout: 60_000,
  expect: { timeout: 15_000 },
  /* SQLite + single API process: high parallelism causes flaky "database is locked" / failed fetches. */
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/docs",
      cwd: __dirname,
      timeout: 120_000,
      /* Prefer reusing listeners on 8000/5173 so local runs do not fail when another dev server is up. CI can set PW_NO_REUSE_SERVER=1 to force a clean bind. */
      reuseExistingServer: process.env.PW_NO_REUSE_SERVER !== "1",
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      cwd: path.join(__dirname, "app", "frontend"),
      timeout: 120_000,
      reuseExistingServer: process.env.PW_NO_REUSE_SERVER !== "1",
    },
  ],
});
