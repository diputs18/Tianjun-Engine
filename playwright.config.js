import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_TEST_BASE_URL ?? "http://127.0.0.1:8137";

export default defineConfig({
  testDir: "tests/browser",
  fullyParallel: false,
  workers: process.env.CI ? 1 : 2,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: process.env.PLAYWRIGHT_TEST_BASE_URL
    ? undefined
    : {
        command: "python scripts/browser_test_server.py",
        url: `${baseURL}/health`,
        timeout: 30_000,
        reuseExistingServer: !process.env.CI,
      },
  projects: [
    { name: "desktop-1366", use: { viewport: { width: 1366, height: 768 } } },
    { name: "desktop-1920", use: { viewport: { width: 1920, height: 1080 } } },
  ],
});
