import { test, expect } from "@playwright/test";
import path from "node:path";

test("digest empty state and discovery administration preserve truthful gates", async ({
  page,
}, info) => {
  await page.request.post("/api/locale", { data: { lang: "en" } });
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Catalog studio demo", exact: true })
    .click();
  await expect(page).toHaveURL("/");
  await page.goto("/digests");
  await expect(
    page.getByRole("heading", { name: "No digests yet." }),
  ).toBeVisible();
  await expect(
    page.getByText("No live collection is simulated here.", { exact: false }),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve(
      `../../.impeccable/review/digest-${info.project.name}.png`,
    ),
    fullPage: true,
    animations: "disabled",
  });
  await page.goto("/admin");
  await page
    .getByRole("tab", { name: "Threads discovery", exact: true })
    .click();
  await expect(
    page.getByText("Release gates closed", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run once", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText("No runs yet.", { exact: false })).toBeVisible();
  await page
    .getByRole("button", { name: "Resume collection", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Pause collection", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Pause collection", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Resume collection", exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.resolve(
      `../../.impeccable/review/discovery-${info.project.name}.png`,
    ),
    fullPage: true,
    animations: "disabled",
  });
});

test("multi-flower ANY/ALL filters persist in the URL", async ({
  page,
}, info) => {
  await page.request.post("/api/locale", { data: { lang: "en" } });
  await page.goto("/login");
  await page.getByRole("button", { name: "Explore demo", exact: true }).click();
  await expect(page).toHaveURL("/");
  await page.goto("/search");
  if (info.project.name === "mobile")
    await page.getByRole("button", { name: "Filters", exact: true }).click();
  const filters =
    info.project.name === "mobile"
      ? page.getByRole("dialog", { name: "Filters", exact: true })
      : page.locator(".desktop-filter-content");
  await filters
    .getByLabel("Choose flower types", { exact: true })
    .selectOption(["rose", "sunflower"]);
  await filters
    .getByRole("combobox", { name: "Flower matching", exact: true })
    .selectOption("all");
  await filters
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await expect(page).toHaveURL(/flower=rose/);
  await expect(page).toHaveURL(/flower_mode=all/);
  await expect(page.locator(".bouquet-card")).toHaveCount(0);
});
