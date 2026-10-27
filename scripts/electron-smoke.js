const { _electron: electron } = require("playwright");
const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

(async () => {
  const root = path.resolve(__dirname, "..");
  const testProfile = fs.mkdtempSync(
    path.join(os.tmpdir(), "lead-extractor-smoke-"),
  );
  const app = await electron.launch({
    args: [root, `--user-data-dir=${testProfile}`],
    cwd: root,
    env: { ...process.env, LEAD_EXTRACTOR_PORT: "18788" },
  });
  try {
    const page = await app.firstWindow();
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(String(error)));
    await page.waitForLoadState("domcontentloaded");
    try {
      await page.waitForFunction(
        () => document.documentElement.classList.contains("electron-app"),
        null,
        { timeout: 30000 },
      );
    } catch (error) {
      console.error("Electron page URL:", page.url());
      console.error("Electron page title:", await page.title());
      console.error(
        "Electron preload available:",
        await page
          .evaluate(() => Boolean(window.leadFinderWindow))
          .catch(() => false),
      );
      console.error("Electron page errors:", pageErrors);
      throw error;
    }
    assert.strictEqual(await page.locator("header").isVisible(), true);
    assert.strictEqual(await page.locator("#windowBack").isVisible(), true);
    assert.strictEqual(await page.locator("#windowClose").isVisible(), true);
    assert.strictEqual(await page.locator("#maintenanceCard").count(), 1);
    await page.waitForFunction(
      () =>
        document.querySelectorAll("#connectionCards .connection-card")
          .length === 5,
    );
    assert.strictEqual(
      await page
        .locator("#connectionCards")
        .textContent()
        .then((text) => text.includes("Google Sheets")),
      true,
    );
    assert.strictEqual(
      await page.evaluate(
        () => typeof window.leadFinderWindow?.maintenanceStatus === "function",
      ),
      true,
    );
    assert.strictEqual(
      await page
        .locator("#windowClose")
        .evaluate((node) => node.closest("header") !== null),
      true,
    );

    await app.evaluate(({ BrowserWindow }) => {
      BrowserWindow.getAllWindows()[0].setSize(960, 700);
    });
    await page.waitForTimeout(250);
    if (
      (await page
        .locator("#menuDensityToggle")
        .getAttribute("aria-pressed")) === "true"
    ) {
      await page.locator("#menuDensityToggle").click();
    }
    assert.strictEqual(
      await page
        .locator(".sidebar")
        .evaluate((node) => getComputedStyle(node).width),
      "76px",
    );
    assert.strictEqual(
      await page
        .locator(".sidebar")
        .evaluate((node) => getComputedStyle(node).left),
      "10px",
    );
    assert.strictEqual(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
      true,
    );

    await page.locator("#menuDensityToggle").click();
    assert.strictEqual(
      await page.locator("#menuDensityToggle").getAttribute("aria-pressed"),
      "true",
    );
    assert.strictEqual(
      await page
        .locator(".sidebar")
        .evaluate((node) => getComputedStyle(node).width),
      "236px",
    );
    assert.strictEqual(await page.locator(".brand-text").isVisible(), true);
    await page.locator("#menuDensityToggle").click();

    const startingHash = await page.evaluate(() => location.hash);
    await page.locator('nav a[href="#history"]').click();
    await page.waitForFunction(() => location.hash === "#history");
    await page.locator("#windowBack").click();
    await page.waitForFunction((hash) => location.hash === hash, startingHash);

    await app.evaluate(({ BrowserWindow }) => {
      BrowserWindow.getAllWindows()[0].setSize(1380, 880);
    });
    await page.waitForTimeout(150);
    assert.strictEqual(await page.locator(".brand-text").isVisible(), false);
    console.log(
      "Electron smoke test passed: borderless window, detached thin/wide menu, resizing and Back navigation.",
    );
  } finally {
    await app.close();
    fs.rmSync(testProfile, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
