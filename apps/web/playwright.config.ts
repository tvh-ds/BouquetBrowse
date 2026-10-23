import { defineConfig } from "@playwright/test";
import path from "node:path";
const python = path.resolve(
  process.platform === "win32"
    ? "../api/.venv/Scripts/python.exe"
    : "../api/.venv/bin/python",
);
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    {
      name: "mobile",
      use: {
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: `"${python}" -m uvicorn bouquetbrowse.api:app --host 127.0.0.1 --port 8000 --no-access-log`,
      url: "http://127.0.0.1:8000/health/ready",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
      env: {
        APP_MODE: "demo",
        DATABASE_URL:
          process.env.E2E_DATABASE_URL ||
          `sqlite:///${path.resolve("../../.data/e2e.db").replaceAll("\\", "/")}`,
        INTERNAL_API_TOKEN: "localhost-proxy-demo-token",
      },
    },
    {
      command: "npm run start -- --port 3000",
      url: "http://127.0.0.1:3000/login",
      reuseExistingServer: !process.env.CI,
      timeout: 60000,
      env: {
        APP_MODE: "demo",
        API_URL: "http://127.0.0.1:8000",
        INTERNAL_API_TOKEN: "localhost-proxy-demo-token",
      },
    },
  ],
});
