const { defineConfig } = require("@playwright/test");
const path = require("node:path");

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "auth-session.spec.cjs",
  globalSetup: require.resolve("./auth-session.setup.cjs"),
  workers: 1,
  timeout: 20000,
  reporter: "list",
  outputDir: path.resolve(__dirname, "../../../test-results/auth-session-20261120"),
  use: {
    baseURL: "http://127.0.0.1:15486",
    browserName: "chromium",
    serviceWorkers: "block",
    launchOptions: { executablePath: process.env.PW_CHROMIUM_EXECUTABLE || undefined },
  },
});
