const { defineConfig } = require('@playwright/test');
const path = require('node:path');

// All requests are fulfilled by the tests. No server or database is used.
module.exports = defineConfig({
  testDir: path.join(__dirname, 'tests'),
  testMatch: 'candidate-reminder-state-20261120.spec.cjs',
  metadata: { offlineCandidateState: true },
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: 'list',
  outputDir: path.join(__dirname, '../test-results/candidate-reminder-state-20261120'),
  use: {
    baseURL: 'http://127.0.0.1:15489',
    browserName: 'chromium',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
