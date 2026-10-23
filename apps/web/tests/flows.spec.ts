import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
async function login(page: Page, admin = false) {
  await page.request.post("/api/locale", { data: { lang: "en" } });
  await page.goto("/login");
  await page
    .getByRole("button", {
      name: admin ? "Catalog studio demo" : "Explore demo",
      exact: true,
    })
    .click();
  await expect(page).toHaveURL("/");
}
test("private access, discovery, filters and source detail", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await login(page);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Find your kind",
  );
  await expect(page.locator(".bouquet-card")).toHaveCount(12);
  await page.goto("/search?flower=rose&color=pink&max_price=800000");
  await expect(page.locator(".bouquet-card").first()).toBeVisible();
  await page.locator(".bouquet-card").first().getByRole("link").first().click();
  await expect(
    page.getByRole("heading", { name: "Sources & evidence", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Availability: ask seller", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Demonstration seller", { exact: true }),
  ).toBeVisible();
});
test("selection tray, side-by-side comparison and analytics", async ({
  page,
}, testInfo) => {
  await login(page);
  await page
    .locator(".bouquet-card")
    .nth(0)
    .getByRole("button", { name: "Add to comparison", exact: true })
    .click();
  await page
    .locator(".bouquet-card")
    .nth(1)
    .getByRole("button", { name: "Add to comparison", exact: true })
    .click();
  await page
    .getByRole("complementary", { name: "Compare" })
    .getByRole("link", { name: "Compare", exact: true })
    .click();
  await expect(page.locator(".comparison-column")).toHaveCount(2);
  await expect(
    page.getByRole("heading", {
      name: "A little price perspective",
      exact: true,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve(
      `../../.impeccable/review/compare-${testInfo.project.name}.png`,
    ),
    fullPage: true,
    animations: "disabled",
  });
  const previous = new URL(page.url()).searchParams.get("ids")!.split(",");
  await page
    .locator(".comparison-column")
    .first()
    .getByRole("button", { name: "Remove from comparison", exact: true })
    .click();
  await expect(page.locator(".comparison-column")).toHaveCount(1);
  await expect(page).toHaveURL(new RegExp(`ids=${previous[1]}`));
  await page.goto("/analytics");
  await expect(
    page.getByText("Fictional demonstration statistics, not market prices.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Advertisements in this cohort",
      exact: true,
    }),
  ).toBeVisible();
});
test("empty results and tester authorization", async ({ page }) => {
  await login(page);
  await page.goto("/search?q=zzzz-no-flower-match");
  await expect(
    page.getByRole("heading", {
      name: "No bouquets match just yet",
      exact: true,
    }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/admin/jobs")).status()).toBe(403);
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", {
      name: "Reviewer access required.",
      exact: true,
    }),
  ).toBeVisible();
});
test("studio source capabilities, importer and responsive screenshots", async ({
  page,
}, testInfo) => {
  await login(page, true);
  await page.goto("/admin");
  await page.getByRole("tab", { name: "Sources", exact: true }).click();
  await expect(
    page.getByText("Threads keyword discovery", { exact: true }),
  ).toBeVisible();
  expect(
    await page
      .getByRole("button", { name: "Sync", exact: true })
      .nth(1)
      .isDisabled(),
  ).toBeTruthy();
  await page.getByRole("tab", { name: "Import", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Import JSON", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve(
      `../../.impeccable/review/admin-${testInfo.project.name}.png`,
    ),
    fullPage: true,
    animations: "disabled",
  });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  await page.locator(".bouquet-card img").first().waitFor({ state: "visible" });
  await expect(page.locator("body")).toHaveJSProperty(
    "scrollWidth",
    await page.locator("body").evaluate((el) => el.clientWidth),
  );
  await page.screenshot({
    path: path.resolve(`../../.impeccable/review/${testInfo.project.name}.png`),
    fullPage: true,
    animations: "disabled",
  });
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Filters", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Filters" })).toBeVisible();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(
      page.getByRole("dialog", { name: "Filters" }),
    ).not.toBeVisible();
  }
});
