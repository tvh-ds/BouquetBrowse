import { test, expect } from "@playwright/test";

test("public-page preview reports restrictions and creates an editable draft", async ({
  page,
}) => {
  await page.request.post("/api/locale", { data: { lang: "en" } });
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Catalog studio demo", exact: true })
    .click();
  await expect(page).toHaveURL("/");
  await page.goto("/admin");
  await page.getByRole("tab", { name: "Import", exact: true }).click();
  const input = page.getByRole("textbox", {
    name: "Public post URL",
    exact: true,
  });
  await input.fill("https://www.threads.com/share/SYNTHETIC/");
  await page.route("**/api/v1/admin/pages/preview", (route) =>
    route.fulfill({
      status: 409,
      json: { error: { message: "Source restricted anonymous access." } },
    }),
  );
  await page
    .getByRole("button", { name: "Collect page & draft", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "restricted anonymous access",
  );
  await expect(
    page.getByRole("textbox", { name: "Import JSON", exact: true }),
  ).toHaveValue("");
  await page.unroute("**/api/v1/admin/pages/preview");
  await page.route("**/api/v1/admin/pages/preview", (route) =>
    route.fulfill({
      json: {
        parser_version: "public-html-v1",
        warnings: ["Publication time is missing."],
        draft: {
          platform: "threads",
          platform_post_id: "SYNTHETIC",
          username: "fictional.florist",
          caption: "Bó hoa 650k",
          published_at: null,
          rights_confirmed: false,
        },
      },
    }),
  );
  await page
    .getByRole("button", { name: "Collect page & draft", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Import JSON", exact: true }),
  ).toHaveValue(/fictional.florist/);
  await expect(
    page.getByText("Publication time is missing.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Import JSON", exact: true }),
  ).toHaveValue(/"rights_confirmed": false/);
  await expect(
    page.getByRole("button", { name: "Import & queue", exact: true }),
  ).toBeEnabled();
});
