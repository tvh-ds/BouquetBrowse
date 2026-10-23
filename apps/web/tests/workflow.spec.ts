import { test, expect } from "@playwright/test";
import { spawnSync } from "node:child_process";
import path from "node:path";

test("operator import, worker extraction, review and source-linked publication", async ({
  page,
}, info) => {
  await page.request.post("/api/locale", { data: { lang: "en" } });
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Catalog studio demo", exact: true })
    .click();
  await expect(page).toHaveURL("/");
  await page.goto("/admin");
  await page.getByRole("tab", { name: "Import", exact: true }).click();
  const payload = {
    posts: [
      {
        platform: "operator",
        platform_post_id: `e2e-${info.project.name}-${Date.now()}`,
        username: "fixture_florist",
        seller_name: "E2E Fictional Florist",
        seller_slug: "e2e-fictional-florist",
        district: "Ba Đình",
        city: "Hanoi",
        source_url: "https://example.com/bouquet-research-fixture",
        published_at: new Date().toISOString(),
        caption:
          "Bó hoa hồng màu hồng, 20 cành. Giá 650k. Đặt trước 2 ngày. Có giao hàng. Phí ship 30k.",
        media_urls: [],
        rights_confirmed: true,
      },
    ],
  };
  await page
    .getByRole("textbox", { name: "Import JSON", exact: true })
    .fill(JSON.stringify(payload, null, 2));
  await page
    .getByRole("button", { name: "Import & queue", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Imported");
  // Exercise the real separate worker process against this test server's DB.
  const python = path.resolve(
    process.platform === "win32"
      ? "../api/.venv/Scripts/python.exe"
      : "../api/.venv/bin/python",
  );
  const result = spawnSync(
    python,
    [
      "-c",
      "from bouquetbrowse.worker import run_once\nfor _ in range(4): run_once()",
    ],
    {
      env: {
        ...process.env,
        APP_MODE: "demo",
        DATABASE_URL:
          process.env.E2E_DATABASE_URL ||
          `sqlite:///${path.resolve("../../.data/e2e.db").replaceAll("\\", "/")}`,
      },
      encoding: "utf8",
      timeout: 30000,
    },
  );
  expect(result.status, result.stderr).toBe(0);
  await page.reload();
  await page.getByRole("tab", { name: /^Review \(/ }).click();
  const item = page
    .locator(".review-item")
    .filter({ hasText: "E2E Fictional Florist" })
    .last();
  await expect(item).toBeVisible();
  await item
    .getByRole("textbox", { name: "Decision reason", exact: true })
    .fill(
      "Checked the fictional source price, count, and product association.",
    );
  await item
    .getByRole("button", { name: "Accept & publish", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Review decision saved");
  await page.goto("/search?q=E2E%20Fictional%20Florist");
  await page.locator(".bouquet-card").first().getByRole("link").first().click();
  await expect(
    page
      .getByRole("link", { name: "View original seller", exact: true })
      .first(),
  ).toHaveAttribute("href", "https://example.com/bouquet-research-fixture");
  await expect(
    page.getByText("650.000 ₫", { exact: true }).first(),
  ).toBeVisible();
});
