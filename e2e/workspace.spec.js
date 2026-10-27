const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const fs = require("node:fs");
test.beforeEach(async ({ page }) => {
  page.on("pageerror", (err) => {
    throw err;
  });
  page.on("response", (r) => {
    if (r.status() >= 500) throw Error("HTTP " + r.status() + " " + r.url());
  });
  await page.route("**/api/ai/status", (route) =>
    route.fulfill({
      json: {
        available: false,
        models: [],
        message: "Synthetic test: local AI is offline. Scraping still works.",
      },
    }),
  );
});
test("discovery, history, sources and accessibility at desktop/mobile", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Build your search" }),
  ).toBeVisible();
  await page.getByLabel("Business or service").fill("Roofing");
  await expect(
    page.getByText("roofing contractor", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Search history/ }).click();
  await expect(
    page.getByRole("heading", { name: "Pick up where you left off." }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Data sources/ }).click();
  await expect(
    page.getByRole("heading", { name: "Google Maps · Chrome" }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Business registries/ }).click();
  await expect(
    page.getByRole("heading", { name: "Search reviewed business registries." }),
  ).toBeVisible();
  await expect(page.locator("#registryCards .registry-card")).toHaveCount(11);
  await page.locator("#registryCountry").selectOption("Australia");
  await page.getByRole("button", { name: "Find directories" }).click();
  await expect(page.locator("#registryCards .registry-card")).toHaveCount(3);
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.getByRole("link", { name: /Discover businesses/ }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: "replica/clone-screens/S01-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: /Find businesses/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "replica/clone-screens/S01-mobile.png",
    fullPage: true,
  });
});
test("open actual saved run, filter, inspect evidence, diagnostics and export", async ({
  page,
  request,
}) => {
  const history = await (await request.get("/api/jobs")).json();
  const completed = history
    .filter((j) => j.count > 0 && ["complete", "partial"].includes(j.status))
    .sort(
      (a, b) =>
        Number(Boolean(b.params.target)) - Number(Boolean(a.params.target)) ||
        b.count - a.count,
    )[0];
  test.skip(!completed, "Requires a completed live search");
  await page.goto("/#history");
  const savedRun = page.locator(`.history-open[data-id="${completed.id}"]`);
  const savedGroup = page
    .locator("details.history-group")
    .filter({ has: savedRun });
  await savedGroup.locator(":scope > summary").click();
  await expect(
    page
      .locator(
        `.history-preview[data-preview-id="${completed.id}"] .history-businesses`,
      )
      .first(),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await savedGroup.locator(":scope > summary").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "replica/clone-screens/history-groups.png" });
  await savedRun.click();
  await expect(page.locator("#resultHeading")).toHaveText(
    completed.count + " businesses · " + completed.params.niche,
  );
  await page
    .getByLabel("Contact filter", { exact: true })
    .selectOption("email");
  const count = await page.locator(".detail-button").count();
  if (count) {
    await page.locator(".detail-button").first().click();
    await expect(
      page.getByRole("heading", { name: "Contact evidence", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Close business details" }).click();
  }
  await page.getByRole("tab", { name: "Run diagnostics" }).click();
  await expect(
    page.getByRole("heading", { name: "Search timeline" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Verification" }).click();
  await expect(
    page.getByRole("heading", { name: "Second-round public verification" }),
  ).toBeVisible();
  const data = await request.get("/api/download/" + completed.id + "/csv");
  expect(data.ok()).toBeTruthy();
  expect(await data.text()).toContain("source_url");
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({
    path: "replica/clone-screens/S04-diagnostics.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Business list" }).click();
  await page.getByLabel("Contact filter", { exact: true }).selectOption("all");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .locator("#resultSection")
    .screenshot({ path: "replica/clone-screens/S02-results.png" });
  await page.evaluate(() =>
    document.getElementById("resultSection").scrollIntoView({ block: "start" }),
  );
  await page.screenshot({
    path: "replica/clone-screens/dashboard-preview.png",
  });
});

test("history groups saved research and lazily shows scraped results", async ({
  page,
}) => {
  const created = "2026-10-21T10:00:00Z";
  const summaries = [
    {
      id: "synthetic-history-complete",
      created_at: created,
      status: "complete",
      count: 7,
      message: "Synthetic saved run only",
      params: { niche: " SYNTHETIC Hood Cleaning ", location: "Dallas, Texas" },
    },
    {
      id: "synthetic-history-empty",
      created_at: created,
      status: "failed",
      count: 0,
      message: "SYNTHETIC TEST: source returned no results.",
      params: { niche: "synthetic   hood cleaning", location: "Austin, Texas" },
    },
    {
      id: "synthetic-history-unavailable",
      created_at: created,
      status: "complete",
      count: 1,
      message: "Synthetic unavailable run",
      params: { niche: "SYNTHETIC Roofing", location: "Miami, Florida" },
    },
  ];
  const rows = Array.from({ length: 7 }, (_, i) => ({
    name:
      i === 0
        ? "SYNTHETIC TEST — provider <em>literal</em>"
        : `SYNTHETIC TEST — provider ${i + 1}`,
    city: "Dallas, Texas",
    phone: i === 0 ? "+1 555-010-2026" : "",
    email: i === 0 ? "synthetic@example.test" : "",
    website: `https://example.test/business/${i + 1}`,
    source: "website_input",
    source_url: `https://example.test/evidence/${i + 1}`,
    match_status: "service_match",
  }));
  const fullJobs = {
    "synthetic-history-complete": {
      ...summaries[0],
      rows,
      stats: { phones: 1, emails: 1, websites: 7 },
      providers: {},
      events: [],
    },
    "synthetic-history-empty": {
      ...summaries[1],
      rows: [],
      stats: {},
      providers: {},
      events: [],
    },
  };
  const fetches = {};
  let starts = 0;
  await page.addInitScript(() => localStorage.removeItem("leadfinder.lastJob"));
  await page.route("**/api/jobs", (route) =>
    route.fulfill({ json: summaries }),
  );
  await page.route("**/api/jobs/*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/").pop();
    fetches[id] = (fetches[id] || 0) + 1;
    return fullJobs[id]
      ? route.fulfill({ json: fullJobs[id] })
      : route.fulfill({
          status: 404,
          json: { error: "Synthetic fixture: historical run unavailable" },
        });
  });
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/api/search")) starts++;
  });
  await page.goto("/#history");
  const groups = page.locator("#historyList details.history-group");
  await expect(groups).toHaveCount(2);
  expect(
    await groups.evaluateAll((nodes) => nodes.every((node) => !node.open)),
  ).toBeTruthy();
  expect(Object.values(fetches).reduce((n, value) => n + value, 0)).toBe(0);
  const hood = page.locator(
    'details.history-group[data-group="synthetic hood cleaning"]',
  );
  await expect(hood.locator("article.history-item")).toHaveCount(2);
  await hood.locator(":scope > summary").click();
  const complete = page.locator(
    '.history-preview[data-preview-id="synthetic-history-complete"]',
  );
  await expect(complete.getByText(rows[0].name, { exact: true })).toBeVisible();
  await expect(
    complete.getByText(rows[0].phone, { exact: true }),
  ).toBeVisible();
  await expect(
    complete.getByText(rows[0].email, { exact: true }),
  ).toBeVisible();
  await expect(
    complete.locator(`a[href="${rows[0].source_url}"]`),
  ).toBeVisible();
  await expect(complete).toContainText("Showing 5 of 7");
  await expect(
    complete.getByText(rows[5].name, { exact: true }),
  ).not.toBeVisible();
  await complete.locator("details.history-more > summary").click();
  await expect(complete.getByText(rows[5].name, { exact: true })).toBeVisible();
  await expect(complete.locator("em")).toHaveCount(0);
  const empty = page.locator(
    '.history-preview[data-preview-id="synthetic-history-empty"]',
  );
  await expect(empty).toContainText(
    "SYNTHETIC TEST: source returned no results.",
  );
  expect(fetches["synthetic-history-complete"]).toBe(1);
  expect(fetches["synthetic-history-empty"]).toBe(1);
  expect(fetches["synthetic-history-unavailable"] || 0).toBe(0);
  await hood.locator(":scope > summary").click();
  await hood.locator(":scope > summary").click();
  await expect(complete.getByText(rows[0].name, { exact: true })).toBeVisible();
  expect(fetches["synthetic-history-complete"]).toBe(1);
  expect(fetches["synthetic-history-empty"]).toBe(1);
  const roofing = page.locator(
    'details.history-group[data-group="synthetic roofing"]',
  );
  await roofing.locator(":scope > summary").click();
  await expect(roofing).toContainText("Could not load this run");
  expect(fetches["synthetic-history-unavailable"]).toBe(1);
  expect(starts).toBe(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
});

test("seller profile qualification, facts and assumptions stay inspectable", async ({
  page,
}) => {
  const row = {
    name: "SYNTHETIC TEST — solo service provider",
    city: "Dallas, Texas",
    source: "public_profile",
    source_url: "https://www.thumbtack.com/tx/dallas/cleaning/test/service/123",
    profile_url:
      "https://www.thumbtack.com/tx/dallas/cleaning/test/service/123",
    website: "",
    score: 10,
    operator_type: "solo_provider",
    operator_confidence: "self_reported",
    operator_evidence: JSON.stringify([
      {
        status: "self_reported",
        excerpt: "Synthetic fixture: I work alone.",
        url: "https://example.test/about",
      },
    ]),
    facts: JSON.stringify([
      {
        field: "service",
        value: "Synthetic fixture: public service description",
        status: "observed_published",
        url: "https://example.test",
        basis: "test fixture",
      },
    ]),
    assumptions: JSON.stringify(["Service area still needs confirmation."]),
    quality_flags: JSON.stringify(["missing_email", "missing_phone"]),
    evidence_score: 35,
    source_strength: "marketplace_profile",
    match_status: "service_match",
  };
  const fixture = {
    id: "fixture",
    created_at: new Date().toISOString(),
    status: "complete",
    message: "One synthetic fixture",
    params: { niche: "Test service" },
    count: 1,
    rows: [row],
    stats: {
      phones: 0,
      emails: 0,
      websites: 0,
      matches: 1,
      profiles: 1,
      individuals: 1,
      independents: 1,
    },
    providers: {},
    events: [],
  };
  await page.route("**/api/jobs/fixture", (route) =>
    route.fulfill({ json: fixture }),
  );
  await page.addInitScript(() =>
    localStorage.setItem("leadfinder.lastJob", "fixture"),
  );
  await page.goto("/");
  await page
    .getByLabel("Evidence filter", { exact: true })
    .selectOption("profile");
  await page
    .getByLabel("Operator type", { exact: true })
    .selectOption("solo_provider");
  await expect(
    page.getByRole("link", { name: /View public seller profile/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /View details for SYNTHETIC TEST/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Observed facts and source claims" }),
  ).toBeVisible();
  await expect(
    page.getByText("Service area still needs confirmation."),
  ).toBeVisible();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
});

test("five research stages, individual-provider focus and US sampling preview", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Business or service").fill("Hood Cleaning");
  await expect(
    page.getByRole("heading", { name: "Five-stage research plan" }),
  ).toBeVisible();
  await page
    .getByLabel("Search focus", { exact: true })
    .selectOption("individuals");
  await page
    .getByLabel("Geographic coverage", { exact: true })
    .selectOption("usa");
  await page
    .locator("summary")
    .filter({ hasText: "Sources, cities & query preview" })
    .click();
  await expect(page.locator("#strategyPreview")).toContainText(
    "owner operated",
  );
  await expect(page.locator("#coverageSummary")).toContainText(
    "scheduled locations",
  );
  await expect(page.locator("#researchStages")).toContainText(
    "Evidence analyst",
  );
  await expect(page.locator("#strategyPreview")).toContainText("IKECA");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.screenshot({
    path: "replica/clone-screens/research-plan-mobile.png",
    fullPage: true,
  });
});

test("historical library prepares a separate recheck without starting it", async ({
  page,
  request,
}) => {
  const snapshot = await (await request.get("/api/library")).json();
  expect(snapshot.record_count).toBe(44);
  expect(snapshot.source_row_count).toBe(45);
  expect(snapshot.records.reduce((n, r) => n + r.provenance.length, 0)).toBe(
    45,
  );
  const peak = snapshot.records.find((r) => r.name.startsWith("Peak Kitchen"));
  let starts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/api/search")) starts++;
  });
  await page.goto("/#library");
  await expect(
    page.getByRole("heading", {
      name: "Finished research, compiled and organized.",
    }),
  ).toBeVisible();
  await expect(page.locator("#librarySummary")).toContainText(
    "44 historical references",
  );
  await page
    .getByLabel("Search research collections and historical prospects", {
      exact: true,
    })
    .fill("Peak Kitchen");
  await page.locator(`[data-id="${peak.id}"]`).check();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
  await page.getByRole("button", { name: "Prepare website recheck" }).click();
  await expect(
    page.getByLabel("Research profile", { exact: true }),
  ).toHaveValue("hood_automation");
  await expect(page.locator("#source")).toHaveValue("websites");
  await expect(page.locator("#urls")).toHaveValue(peak.website);
  await expect(page.locator("#location")).toHaveValue(
    [peak.city, peak.state].filter(Boolean).join(", "),
  );
  expect(starts).toBe(0);
  await page.getByRole("link", { name: /Your research library/ }).click();
  await page
    .getByLabel("Search research collections and historical prospects", {
      exact: true,
    })
    .fill("");
  await page.setViewportSize({ width: 1440, height: 950 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("button", { name: "Prepare website recheck" }),
  ).toBeInViewport();
  await page.screenshot({ path: "replica/clone-screens/tedt-library.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("compiled research stays grouped, opens full details and feeds outreach", async ({
  page,
}) => {
  const row = {
    name: "Organized Roofing Co",
    address: "1 Main St, Dallas, TX",
    city: "Dallas",
    phone: "214-555-0100",
    email: "owner@organized.test",
    website: "https://organized.test",
    source_url: "https://maps.example/organized",
    source: "Google Maps",
    score: 91,
    entity_id: "company-fixture",
    contact_confidence: 90,
    next_best_action: "ready_for_outreach",
    next_action_reason:
      "Verified evidence and a recommended contact are available.",
    match_status: "service_match",
    operator_type: "independent_operator",
    email_quality: JSON.stringify({
      recommended: [
        {
          email: "owner@organized.test",
          type: "named_or_role_contact",
          basis: "published",
          recommended: true,
        },
      ],
      excluded: [],
    }),
    duplicate_summary: JSON.stringify([
      {
        name: "Organized Roofing",
        source: "web discovery",
        source_url: "https://organized.test/about",
        reason: "same website",
      },
    ]),
    verification: JSON.stringify({
      status: "complete",
      checked_at: "2026-10-23",
      website: { status: "reachable" },
      socials: { linkedin: { url: "https://linkedin.com/company/organized" } },
      ads: { status: "not_verified", tracking_signals: [] },
      reviews: {
        google_maps: { rating: "4.8", review_count: 42 },
        other_sources: [],
      },
    }),
  };
  const collection = {
    id: "compiled-fixture",
    job_id: "compiled-fixture",
    title: "Roofing · Dallas, Texas",
    niche: "Roofing",
    location: "Dallas, Texas",
    created_at: "2026-10-23T10:00:00+05:00",
    record_count: 1,
    rows: [row],
    organization: {
      duplicates_consolidated: 1,
      recommended_email_records: 1,
      ai_status: "complete",
    },
  };
  await page.route("**/api/library", (route) =>
    route.fulfill({
      json: {
        collections: [collection],
        compiled_record_count: 1,
        records: [],
        record_count: 0,
        source_row_count: 0,
      },
    }),
  );
  await page.route("**/api/intelligence/overview", (route) =>
    route.fulfill({
      json: {
        companies: 1,
        contacts: 1,
        evidence_claims: 1,
        changes_detected: 0,
        open_actions: { ready_for_outreach: 1 },
        outcomes: {},
        niche_packs: 1,
        experiments: 0,
        performance: { positive_outcomes: 0 },
      },
    }),
  );
  await page.route("**/api/intelligence/queue", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/intelligence/entities/company-fixture", (route) =>
    route.fulfill({
      json: {
        company: row,
        first_seen: "2026-10-23T10:00:00Z",
        last_seen: "2026-10-23T10:00:00Z",
        locations: [
          {
            address: row.address,
            city: row.city,
            source_url: row.source_url,
            last_seen: "2026-10-23",
          },
        ],
        contacts: [{ email: row.email, confidence: 90, status: "observed" }],
        evidence: [
          {
            field: "email",
            value: row.email,
            source_url: row.website,
            basis: "published",
            observed_at: "2026-10-23",
          },
        ],
        outcomes: [],
        browser_checkpoints: [],
      },
    }),
  );
  await page.route("**/api/jobs/compiled-fixture", (route) =>
    route.fulfill({
      json: {
        ...collection,
        status: "complete",
        params: { niche: "Roofing", location: "Dallas, Texas" },
      },
    }),
  );
  await page.goto("/#library");
  await page.getByText("Roofing · Dallas, Texas", { exact: true }).click();
  await expect(
    page.getByText("Organized Roofing Co", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "View research details for Organized Roofing Co",
    })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Merged duplicate sources",
  );
  await expect(page.getByRole("dialog")).toContainText("Organized Roofing");
  await expect(page.getByRole("dialog")).toContainText(
    "Connected company history",
  );
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("link", { name: /Outreach campaigns/ }).click();
  await page.getByRole("tab", { name: "New campaign" }).click();
  await expect(page.locator("#campaignJob")).toContainText(
    "Roofing · Dallas, Texas · 1 organized prospects",
  );
});

test("opportunity details separate supported scores, unknowns and published claims", async ({
  page,
}) => {
  const signals = [
    {
      kind: "manual_workflow",
      value: "We manually prepare reports",
      excerpt: "SYNTHETIC FIXTURE: We manually prepare reports.",
      url: "https://example.test/workflow",
      basis: "published_page_claim",
    },
  ];
  const row = {
    name: "SYNTHETIC TEST — workflow",
    source: "website_input",
    city: "Dallas",
    score: 30,
    evidence_score: 35,
    match_status: "service_match",
    decision_maker: "",
    research_profile: "hood_automation",
    opportunity_score: 20,
    workflow_signals: JSON.stringify(signals),
    opportunity: JSON.stringify({
      status: "partial",
      coverage: 25,
      supported_points: 20,
      dimensions: {
        pain: { value: 8, weight: 25, reason: "Explicit manual statement" },
        capacity: { value: null, weight: 20, reason: "Budget unknown" },
      },
      assumptions: ["Reports alone do not prove manual work."],
    }),
  };
  const fixture = {
    id: "opportunity-fixture",
    status: "complete",
    message: "Synthetic workflow fixture",
    params: { niche: "Test service" },
    count: 1,
    rows: [row],
    stats: {},
    providers: {},
    events: [],
  };
  await page.route("**/api/jobs/opportunity-fixture", (r) =>
    r.fulfill({ json: fixture }),
  );
  await page.addInitScript(() =>
    localStorage.setItem("leadfinder.lastJob", "opportunity-fixture"),
  );
  await page.goto("/");
  await page
    .getByLabel("Workflow evidence", { exact: true })
    .selectOption("manual_workflow");
  await expect(page.getByText("Opportunity: 20 supported pts")).toBeVisible();
  await page
    .getByRole("button", { name: /View details for SYNTHETIC TEST/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Workflow & offer research" }),
  ).toBeVisible();
  await expect(
    page.getByText(/20\/100 supported opportunity points/),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Unknown", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("SYNTHETIC FIXTURE: We manually prepare reports."),
  ).toBeVisible();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
});

test("local AI suggestions require approval and reviews retain the original lead target", async ({
  page,
}) => {
  const model = "qwen3.5:4b";
  const id = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  const planTaskId = "dddddddddddddddddddddddddddddddd";
  const reviewTaskId = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";
  const leadRows = [
    {
      name: "SYNTHETIC TEST — no email",
      city: "Dallas, Texas",
      email: "",
      phone: "",
      website: "https://example.test/first",
      source: "website_input",
      source_url: "https://example.test/first",
      score: 10,
      match_status: "service_match",
    },
    {
      name: "SYNTHETIC TEST — email lead",
      city: "Dallas, Texas",
      email: "fixture@example.test",
      phone: "",
      website: "https://example.test/second",
      source: "website_input",
      source_url: "https://example.test/second",
      score: 20,
      match_status: "service_match",
    },
  ];
  let saved = {
    id,
    created_at: "2026-10-21T10:00:00Z",
    status: "complete",
    message: "Synthetic saved AI review fixture",
    params: { niche: "SYNTHETIC service", location: "Dallas, Texas" },
    count: 2,
    rows: leadRows,
    stats: { emails: 1, websites: 2 },
    providers: {},
    events: [],
  };
  const phrases = ["SYNTHETIC specialist cleaning", "SYNTHETIC owner operated"];
  const review = {
    analysis: {
      status: "complete",
      model,
      summary: "SYNTHETIC interpretation, not a verified need.",
      fit: "uncertain",
      reasons: [
        {
          quote: "SYNTHETIC published workflow claim.",
          note: "Needs human review.",
          url: "https://example.test/second",
          source_id: "fixture-source",
        },
      ],
      questions: ["Does the operator want this service?"],
    },
    draft: {
      status: "ready_for_review",
      model,
      subject: "SYNTHETIC subject <b>literal</b>",
      body: 'Hi there,\nSYNTHETIC draft <img src=x onerror="alert(1)">. Nothing was sent.',
    },
  };
  const assists = [];
  let searches = 0;
  await page.addInitScript(
    (jobId) => localStorage.setItem("leadfinder.lastJob", jobId),
    id,
  );
  await page.route("**/api/ai/status", (route) =>
    route.fulfill({
      json: {
        available: true,
        default_model: model,
        models: [
          { name: model, parameter_size: "4B" },
          { name: "synthetic-local:1b", parameter_size: "1B" },
        ],
        message: "SYNTHETIC local model ready; runs only on request.",
      },
    }),
  );
  await page.route(`**/api/jobs/${id}`, (route) =>
    route.fulfill({ json: saved }),
  );
  await page.route("**/api/jobs", (route) =>
    route.fulfill({ json: [{ ...saved, rows: undefined }] }),
  );
  await page.route("**/api/search", (route) => {
    searches++;
    return route.fulfill({
      status: 400,
      json: { error: "A search must not start in the AI fixture" },
    });
  });
  await page.route("**/api/ai/assist", (route) => {
    const payload = route.request().postDataJSON();
    assists.push(payload);
    return route.fulfill({
      json: { id: payload.task === "plan" ? planTaskId : reviewTaskId },
    });
  });
  await page.route("**/api/ai/tasks/*", (route) => {
    const plan = route
      .request()
      .url()
      .endsWith("/" + planTaskId);
    if (!plan)
      saved = {
        ...saved,
        rows: saved.rows.map((row, index) =>
          index === 1
            ? {
                ...row,
                ai_analysis: JSON.stringify(review.analysis),
                ai_draft: JSON.stringify(review.draft),
              }
            : row,
        ),
      };
    return route.fulfill({
      json: {
        status: "complete",
        message: "SYNTHETIC local task complete",
        result: plan
          ? { phrases, notes: ["SYNTHETIC suggestions only."], model }
          : review,
      },
    });
  });
  await page.goto("/");
  await expect(page.getByLabel("Local model", { exact: true })).toHaveValue(
    model,
  );
  await expect(
    page.getByLabel("Local model", { exact: true }).locator("option"),
  ).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Suggest search terms", exact: true }),
  ).toBeEnabled();
  expect(assists).toHaveLength(0);
  await page.locator("#niche").fill("SYNTHETIC service");
  await page.locator("#location").fill("Dallas, Texas");
  await page.locator("details.advanced > summary").click();
  await page.locator("#phrases").fill("SYNTHETIC existing phrase");
  await page
    .getByRole("button", { name: "Suggest search terms", exact: true })
    .click();
  await expect(page.locator("#aiPlanOutput")).toContainText(
    "AI search tags · not applied",
  );
  await expect(page.locator("#aiPlanOutput")).toContainText(phrases[0]);
  await expect(page.locator("#phrases")).toHaveValue(
    "SYNTHETIC existing phrase",
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .locator(".ai-card")
    .screenshot({ path: "replica/clone-screens/local-ai-panel-fixture.png" });
  expect(assists).toEqual([
    {
      task: "plan",
      model,
      niche: "SYNTHETIC service",
      location: "Dallas, Texas",
    },
  ]);
  expect(searches).toBe(0);
  await page.locator("#location").fill("Austin, Texas");
  await expect(
    page.getByRole("button", { name: "Use these phrases", exact: true }),
  ).toBeDisabled();
  await page.locator("#location").fill("Dallas, Texas");
  await expect(
    page.getByRole("button", { name: "Use these phrases", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Use these phrases", exact: true })
    .click();
  await expect(page.locator("#phrases")).toHaveValue(
    ["SYNTHETIC existing phrase", ...phrases].join("\n"),
  );
  expect(assists).toHaveLength(1);
  expect(searches).toBe(0);
  const offer = "SYNTHETIC OFFER: help organize inspection reports.";
  await page
    .getByLabel("Your outreach offer (optional)", { exact: true })
    .fill(offer);
  await page
    .getByLabel("Contact filter", { exact: true })
    .selectOption("email");
  await expect(page.locator(".detail-button")).toHaveCount(1);
  await page
    .getByRole("button", {
      name: "View details for SYNTHETIC TEST — email lead",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Review with local AI", exact: true }),
  ).toBeEnabled();
  expect(assists).toHaveLength(1);
  await page
    .getByRole("button", { name: "Review with local AI", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Outreach draft · not sent",
      exact: true,
    }),
  ).toBeVisible();
  expect(assists[1]).toEqual({
    task: "review",
    model,
    job_id: id,
    row_index: 1,
    offer,
  });
  await expect(page.locator(".ai-draft-body")).toHaveText(review.draft.body);
  await expect(page.locator(".ai-review")).toContainText("ready for review");
  await expect(page.locator(".ai-review img, .ai-review script")).toHaveCount(
    0,
  );
  await expect(page.locator(".ai-review")).toContainText(
    "AI-generated and unverified",
  );
  await expect(page.locator(".ai-review")).toContainText(
    "SYNTHETIC subject <b>literal</b>",
  );
  await expect(
    page.locator('#leadDialog a[href="https://example.test/second"]'),
  ).not.toHaveCount(0);
  await page
    .getByRole("button", { name: "Close business details", exact: true })
    .click();
  await expect(page.getByLabel("Contact filter", { exact: true })).toHaveValue(
    "email",
  );
  await expect(page.locator(".detail-button")).toHaveCount(1);
  expect(saved.rows[0].ai_analysis).toBeUndefined();
  expect(saved.rows[1].email).toBe("fixture@example.test");
  expect(searches).toBe(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(scan.violations).toEqual([]);
});

test("offline local AI leaves ordinary mocked searches and saved evidence usable", async ({
  page,
}) => {
  const id = "cccccccccccccccccccccccccccccccc";
  const row = {
    name: "SYNTHETIC TEST — offline AI search result",
    city: "Dallas, Texas",
    email: "",
    phone: "",
    website: "https://example.test/offline",
    source: "website_input",
    source_url: "https://example.test/offline",
    score: 10,
    match_status: "service_match",
  };
  const fixture = {
    id,
    created_at: "2026-10-21T10:00:00Z",
    status: "complete",
    message: "Synthetic search finished without AI",
    params: { niche: "SYNTHETIC offline service", location: "Dallas, Texas" },
    count: 1,
    rows: [row],
    stats: { websites: 1 },
    providers: {},
    events: [],
  };
  const searches = [];
  let assists = 0;
  await page.addInitScript(() => localStorage.removeItem("leadfinder.lastJob"));
  await page.route("**/api/ai/status", (route) =>
    route.fulfill({
      status: 404,
      json: { error: "SYNTHETIC local model service unavailable" },
    }),
  );
  await page.route("**/api/ai/assist", (route) => {
    assists++;
    return route.fulfill({
      status: 400,
      json: { error: "AI must remain unused while offline" },
    });
  });
  await page.route("**/api/search", (route) => {
    searches.push(route.request().postDataJSON());
    return route.fulfill({ json: { id } });
  });
  await page.route(`**/api/jobs/${id}`, (route) =>
    route.fulfill({ json: fixture }),
  );
  await page.route("**/api/jobs", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.locator("#aiStatus")).toContainText("Scraping still works");
  await expect(page.getByLabel("Local model", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Suggest search terms", exact: true }),
  ).toBeDisabled();
  await page.locator("#niche").fill("SYNTHETIC offline service");
  await page.locator("#location").fill("Dallas, Texas");
  await page.locator("#runButton").click();
  await expect(page.locator("#resultHeading")).toHaveText(
    "1 businesses · SYNTHETIC offline service",
  );
  expect(searches).toHaveLength(1);
  expect(searches[0].niche).toBe("SYNTHETIC offline service");
  await page
    .getByRole("button", { name: "View details for " + row.name, exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Review with local AI", exact: true }),
  ).toBeDisabled();
  await expect(page.locator("#aiReviewStatus")).toContainText(
    "saved data remains usable",
  );
  await expect(
    page.getByRole("heading", { name: "Contact evidence", exact: true }),
  ).toBeVisible();
  expect(assists).toBe(0);
});
