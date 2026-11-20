const { defineConfig } = require("@playwright/test");
const path = require("node:path");

const port = process.env.PW_INTAKE_PORT || "15280";
if (!/^\d{1,5}$/.test(port) || Number(port) < 1 || Number(port) > 65535) throw new Error("Invalid intake test port");
const offline = process.env.PW_INTAKE_OFFLINE === "1";
const baseURL = `http://127.0.0.1:${port}`;
module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "document-intake.spec.cjs",
  workers: 1,
  reporter: "list",
  outputDir: path.join(__dirname, "../../../test-results/document-intake-ui"),
  use: {
    baseURL,
    browserName: "chromium",
    launchOptions: { executablePath: process.env.PW_CHROMIUM_EXECUTABLE || undefined },
  },
  webServer: offline ? undefined : {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${port} --strictPort`,
    cwd: path.join(__dirname, ".."),
    url: baseURL,
    env: { VITE_API_BASE_URL: "/api", VITE_PROXY_TARGET: "http://127.0.0.1:1" },
    reuseExistingServer: false,
  },
});
