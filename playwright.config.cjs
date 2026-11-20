/* eslint-disable @typescript-eslint/no-var-requires */
const { defineConfig, devices } = require("@playwright/test");
const path = require("path");
const { randomUUID } = require("node:crypto");
const API_PORT = process.env.PW_API_PORT || "18080";
const WEB_PORT = process.env.PW_WEB_PORT || "15173";
if (![API_PORT, WEB_PORT].every((port) => /^\d{1,5}$/.test(port) && Number(port) > 0 && Number(port) <= 65535)) {
  throw new Error("Invalid Playwright port");
}
const API_URL = `http://127.0.0.1:${API_PORT}`;
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;
process.env.PW_API_BASE = API_URL;
const storage = path.join(__dirname, ".playwright", "intake-regression", randomUUID());

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
    baseURL: WEB_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python e2e/serve_isolated_backend.py",
      url: `${API_URL}/docs`,
      cwd: __dirname,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        PW_API_PORT: API_PORT,
        PW_STORAGE_DIR: storage,
        ENABLE_TEST_ENDPOINTS: "1",
        DEFAULT_ADMIN_USERNAME: "admin",
        DEFAULT_ADMIN_PASSWORD: "admin12345",
        JWT_SECRET_KEY: randomUUID(),
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: WEB_URL,
      cwd: path.join(__dirname, "app", "frontend"),
      timeout: 120_000,
      reuseExistingServer: false,
      env: { VITE_PROXY_TARGET: API_URL, VITE_API_BASE_URL: "/api" },
    },
  ],
});
