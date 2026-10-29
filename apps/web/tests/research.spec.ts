import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";

const fingerprint = "a".repeat(64);
const root = path.resolve("../..");
const authPath = path.join(
  root,
  ".data",
  `research-test-auth-${createHash("sha256")
    .update(process.env.E2E_DATABASE_URL || "ci-fresh-database")
    .digest("hex")
    .slice(0, 12)}.json`,
);
test.use({ storageState: authPath });
test.beforeAll(async ({ browser, baseURL }) => {
  if (fs.existsSync(authPath)) return;
  const context = await browser.newContext({
    baseURL,
    storageState: { cookies: [], origins: [] },
  });
  const page = await context.newPage();
  await page.request.post("/api/locale", { data: { lang: "en" } });
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Catalog studio demo", exact: true })
    .click();
  await expect(page).toHaveURL("/");
  fs.mkdirSync(path.dirname(authPath), { recursive: true });
  await context.storageState({ path: authPath });
  await context.close();
});

async function workspace(page: Page, configured = false) {
  const submitted: { path: string; body: Record<string, unknown> }[] = [];
  const item = {
    id: "item-fixture",
    offer_id: "offer-fixture",
    media_id: "media-fixture",
    version: 1,
    state: "annotated",
    labels: ["rose"],
    assessable: ["rose", "peony"],
    reviewers: ["fictional-reviewer"],
    seller_group: "seller-fixture",
    image_family: "fictional-family",
    split: "development",
    cost_microusd: 0,
    latency_ms: 0,
  };
  const dataset = {
    id: "dataset-fixture",
    name: "Fictional mixed-bouquet evaluation",
    kind: "synthetic",
    version: 1,
    taxonomy: { rose: ["rose"], peony: ["peony"] },
    items: [item],
  };
  const taxonomy = {
    version: "flowers-v2",
    vocabulary: { rose: ["rose"], peony: ["peony"] },
    items: [
      {
        id: "term-fixture",
        key: "fictional-filler",
        version: "flowers-v2",
        state: "proposed",
        aliases: [],
        fingerprint,
      },
    ],
  };
  const canonical = {
    offers: [
      {
        id: "offer-fixture",
        seller_id: "seller-fixture",
        listing_id: null,
        fingerprint,
        links_hash: fingerprint,
      },
    ],
    configurations: [
      { id: "config-fixture", seller_id: "seller-fixture" },
      { id: "foreign-config", seller_id: "another-seller" },
    ],
    links: [] as {
      id: string;
      offer_id: string;
      configuration_id: string;
      state: string;
      fingerprint: string;
    }[],
  };
  const proof = {
    id: "proof-fixture",
    kind: "recognition",
    state: "pending",
    report_hash: fingerprint,
    configuration_hash: fingerprint,
    report: {
      dataset_kind: "synthetic",
      dataset_ready: false,
      images: 1,
      categories: {
        rose: {
          supported: false,
          sufficiently_sampled: false,
          joint_holdout: { precision: 1, recall: 1, positive: 1, negative: 0 },
        },
      },
    },
  };
  const alert = {
    id: "alert-fixture",
    code: "jobs_failed",
    state: "open",
    version: 1,
    severity: "warning",
    message: "Fictional verification incident: inspect the failed fixture job.",
    details: { count: 1 },
  };
  const capture = {
    id: "capture-fixture",
    sorting: "Recent",
    stop_reason: "partial",
    remaining_expansions: 3,
    coverage: { complete: false },
    messages: [
      {
        version_id: "version-seller",
        post_id: "post-seller",
        author: "fictional_florist",
        account_id: "seller-fixture",
        profile_saved: false,
        text: "Fictional captured conversation: Bên em nhận đặt bó hoa, giao Hà Nội. Hoa hồng và mẫu đơn, 650k.",
        published_at: "2026-10-28T08:00:00Z",
      },
      {
        version_id: "version-buyer",
        post_id: "post-buyer",
        author: "fictional_buyer",
        account_id: "buyer-fixture",
        profile_saved: false,
        text: "Fictional buyer reply: Có giao ngày mai không?",
        published_at: "2026-10-28T08:10:00Z",
      },
    ],
    edges: [
      {
        source_id: "post-buyer",
        target_id: "post-seller",
        kind: "reply_to",
        unresolved_platform_id: null,
      },
    ],
    offers: [
      {
        id: "offer-fixture",
        state: "review",
        seller_id: "seller-fixture",
        listing_id: null,
      },
    ],
  };
  await page.route("**/api/v1/admin/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname.replace(
      "/api/v1/",
      "",
    );
    if (pathname.endsWith("/media/media-fixture")) {
      await route.fulfill({
        contentType: "image/png",
        body: fs.readFileSync(
          path.join(root, "apps/web/public/images/demo-pink.png"),
        ),
      });
      return;
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      submitted.push({ path: pathname, body });
      if (pathname.endsWith("/acknowledge")) alert.state = "acknowledged";
      if (pathname.endsWith("/taxonomy/term-fixture/decision")) {
        taxonomy.items[0].state = "accepted_proposal";
        taxonomy.version = String(body.new_version);
      }
      if (pathname.endsWith("/canonical/link"))
        canonical.links.push({
          id: "link-fixture",
          offer_id: "offer-fixture",
          configuration_id: String(body.configuration_id || "config-fixture"),
          state: "accepted",
          fingerprint,
        });
      if (pathname.endsWith("/unlink")) canonical.links[0].state = "revoked";
      if (pathname.endsWith("/annotation")) {
        item.labels = body.labels as string[];
        item.version++;
        dataset.version++;
      }
      if (pathname.endsWith("/run")) {
        item.state = "completed";
        item.cost_microusd = 100;
        item.latency_ms = 1000;
      }
      await route.fulfill({
        json: {
          id: "proof-fixture",
          version: dataset.version,
          state: "queued",
        },
      });
      return;
    }
    const responses: Record<string, unknown> = {
      "admin/operations/status": {
        recurring_configured: false,
        backups_configured: false,
        readiness: {
          ready: false,
          conversation_proof: false,
          recognition_proof: false,
          live_results: "Not yet validated on real data",
        },
        roles: [
          {
            role: "offer",
            state: "awake",
            stale: false,
            last_seen_at: "2026-10-29T08:00:00Z",
          },
        ],
        coverage: {
          visible_real_listings: 0,
          visible_independent_sellers: 0,
          observed_real_posts: 0,
        },
        model_cost_microusd: 0,
        model_budget_microusd: 100000000,
        alerts: [alert],
        backups: [],
      },
      "admin/discovery/status": {
        enabled: false,
        paused: true,
        settings_version: 1,
        postgres: configured,
        model_configured: configured,
        browser_installed: false,
        release_gates: {},
        publication_enabled: false,
      },
      "admin/conversations": {
        items: [
          {
            id: capture.id,
            url: "https://www.threads.com/@fictional_florist/post/fixture",
            at: "2026-10-29T08:00:00Z",
            sorting: "Recent",
            stop_reason: "partial",
            remaining_expansions: 3,
          },
        ],
      },
      "admin/conversations/capture-fixture": capture,
      "admin/conversations/offers/offer-fixture": {
        id: "offer-fixture",
        state: "review",
        evidence: {
          messages: [],
          media: [
            { media_id: "media-fixture", role: "seller_image", region: null },
          ],
        },
      },
      "admin/curation/taxonomy": taxonomy,
      "admin/curation/canonical": canonical,
      "admin/evaluations": { items: [dataset] },
      "admin/evaluations/dataset-fixture": dataset,
      "admin/pilot/proofs": { items: [proof] },
    };
    if (pathname in responses)
      await route.fulfill({ json: responses[pathname] });
    else await route.continue();
  });
  await page.goto("/admin");
  await page
    .getByRole("tab", { name: "Research & operations", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Runtime health", exact: true }),
  ).toBeVisible();
  return { submitted, dataset, item };
}
async function panel(page: Page, value: string) {
  await page
    .getByRole("combobox", { name: "Research workspace", exact: true })
    .selectOption(value);
}

test("health, conversation evidence and reviewed curation actions are connected", async ({
  page,
}) => {
  const { submitted } = await workspace(page);
  await page.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Acknowledge", exact: true }),
  ).toBeDisabled();
  await panel(page, "conversations");
  await page
    .getByRole("button", { name: "Inspect conversation", exact: true })
    .click();
  await expect(
    page.getByText("Reply to @fictional_florist", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Remaining expansions: 3", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect offer images", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Add to evaluation draft", exact: true })
    .click();
  await expect(page.getByLabel("Selected offer images (JSON)")).toHaveValue(
    /media-fixture/,
  );
  await panel(page, "taxonomy");
  await page
    .getByRole("button", { name: "Review proposal", exact: true })
    .click();
  await page
    .getByLabel("Review reason", { exact: true })
    .fill("Reviewed fictional category for interface verification");
  await page
    .getByRole("button", { name: "Approve new version", exact: true })
    .click();
  await expect(
    page.getByText("Taxonomy decision saved.", { exact: true }),
  ).toBeVisible();
  await panel(page, "canonical");
  await page.getByLabel("Offer to link").selectOption("offer-fixture");
  await expect(
    page.getByLabel("Seller's configuration group").locator("option"),
  ).toHaveCount(2);
  await page
    .getByLabel("Seller's configuration group")
    .selectOption("config-fixture");
  await page
    .getByLabel("Reason for reviewed match")
    .fill("Reviewed seller-supported configuration evidence");
  await page
    .getByRole("button", { name: "Save canonical link", exact: true })
    .click();
  await expect(
    page.getByText("Canonical link saved.", { exact: true }),
  ).toBeVisible();
  await page.getByText("Revoke link", { exact: true }).click();
  await page
    .getByLabel("Revocation reason")
    .fill("Fictional correction preserves the offer identity");
  await page
    .getByRole("button", { name: "Revoke reviewed link", exact: true })
    .click();
  await expect(
    page.getByText("Link revoked; history preserved.", { exact: true }),
  ).toBeVisible();
  expect(
    submitted.find((s) => s.path.endsWith("/canonical/link"))?.body
      .expected_links_hash,
  ).toBe(fingerprint);
});

test("annotation, explicit evaluation and proof review preserve publication gates", async ({
  page,
}) => {
  const { submitted } = await workspace(page, true);
  await panel(page, "evaluation");
  await page
    .getByRole("button", { name: "Open evaluation set", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Annotate image", exact: true })
    .click();
  await page
    .getByRole("listbox", { name: "Visible flower types", exact: true })
    .selectOption(["rose", "peony"]);
  await page
    .getByRole("button", { name: "Save reference annotation", exact: true })
    .click();
  await expect(
    page.getByText("Annotation and review history saved.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Run evaluation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Stage proof report", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Stage proof report", exact: true })
    .click();
  await panel(page, "proofs");
  await page
    .getByRole("button", { name: "Inspect proof report", exact: true })
    .click();
  await expect(
    page.getByText("Synthetic report — ineligible for real-data approval.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve real-data proof", exact: true }),
  ).toHaveCount(0);
  expect(
    submitted.find((s) => s.path.endsWith("/annotation"))?.body
      .expected_version,
  ).toBe(1);
  expect(
    submitted.find((s) => s.path.endsWith("/run"))?.body.expected_version,
  ).toBe(2);
});

test("populated research workspaces remain usable on the shipped viewports", async ({
  page,
}, info) => {
  await workspace(page);
  for (const name of [
    "health",
    "conversations",
    "taxonomy",
    "canonical",
    "evaluation",
    "proofs",
  ]) {
    await panel(page, name);
    if (name === "conversations") {
      await page
        .getByRole("button", { name: "Inspect conversation", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Inspect offer images", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Associated offer images" }),
      ).toBeVisible();
    }
    if (name === "taxonomy")
      await page
        .getByRole("button", { name: "Review proposal", exact: true })
        .click();
    if (name === "canonical")
      await page.getByLabel("Offer to link").selectOption("offer-fixture");
    if (name === "evaluation") {
      await page
        .getByRole("button", { name: "Open evaluation set", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Annotate image", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Run evaluation", exact: true }),
      ).toBeDisabled();
    }
    if (name === "proofs")
      await page
        .getByRole("button", { name: "Inspect proof report", exact: true })
        .click();
    for (const image of await page.locator("img:visible").all()) {
      await image.scrollIntoViewIfNeeded();
      await expect(image).toHaveJSProperty("complete", true);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: path.join(
        root,
        `.impeccable/review/research-${name}-${info.project.name}.png`,
      ),
      fullPage: true,
      animations: "disabled",
    });
  }
});
