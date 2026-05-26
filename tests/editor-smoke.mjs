import { execFile } from "node:child_process";
import { mkdtemp, rm, cp, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { chromium } from "playwright";

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixtureArg = process.argv[2] || "tests/fixtures/2026-05-02-9cd2a2ac";
const device = process.argv[3] || "desktop";
const sourceEngagement = path.resolve(repoRoot, fixtureArg);

async function exists(file) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

async function run(cmd, args, options = {}) {
  return execFileAsync(cmd, args, {
    cwd: repoRoot,
    timeout: options.timeout || 120000,
    maxBuffer: 30 * 1024 * 1024,
  });
}

function fileUrl(file) {
  return pathToFileURL(file).href;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function main() {
  assert(await exists(sourceEngagement), `Missing smoke fixture: ${sourceEngagement}`);

  const tmpRoot = await mkdtemp(path.join(tmpdir(), "ecp-editor-smoke-"));
  const tmpEngagement = path.join(tmpRoot, path.basename(sourceEngagement));
  let browser;
  try {
    await cp(sourceEngagement, tmpEngagement, { recursive: true });

    await run("python", ["scripts/generate-editor.py", "--engagement", tmpEngagement, "--plugin-root", repoRoot]);
    await run("python", [
      "scripts/generate-report.py",
      "--engagement", tmpEngagement,
      "--device", device,
      "--plugin-root", repoRoot,
      "--v2",
      "--skip-editor",
    ]);

    const reportPath = path.join(tmpEngagement, `visual-report-${device}-v2.html`);
    const editorPath = path.join(tmpEngagement, "editor.html");
    assert(await exists(reportPath), `Generated report missing: ${reportPath}`);
    assert(await exists(editorPath), `Generated editor missing: ${editorPath}`);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });

    await page.goto(fileUrl(reportPath));
    assert(await page.locator("button", { hasText: "Open Editor" }).count() >= 1, "Report header lacks Open Editor");
    assert(await page.locator(".detail-btn-editor-queue").count() > 0, "Report lacks Queue edit buttons");
    assert(await page.locator(".detail-btn-editor-open").count() > 0, "Report lacks Open editor buttons");

    await page.locator(".panel-scroll:not([hidden]) .finding-row[data-fid], .panel-scroll:not([hidden]) .priority-ref-row[data-fid]").first().click();
    const fid = await page.locator(".detail-card.visible").getAttribute("data-fid");
    assert(fid, "No active finding detail was selected");

    await page.locator(`.detail-btn-editor-queue[data-fid="${cssEscape(fid)}"]`).click();
    const queued = await page.evaluate(() => {
      const entry = Object.entries(localStorage).find(([key]) => key.startsWith("ecp-editor-picks:"));
      return entry ? JSON.parse(entry[1]) : [];
    });
    assert(Array.isArray(queued) && queued.includes(fid), "Queue edit did not persist the selected finding");

    await page.goto(`${fileUrl(editorPath)}#pick=${encodeURIComponent(fid)}&device=${encodeURIComponent(device)}`);
    await page.waitForSelector("#stage .stage-hud", { timeout: 15000 });

    assert(await page.locator("#doneFinding").count() === 1, "Editor lacks Done Finding");
    assert(await page.locator("#previewToggle").count() === 1, "Editor lacks preview toggle");
    assert(await page.locator("#previewFinding").count() === 1, "Editor lacks Preview Finding");
    assert(await page.locator("#exportFindingBundle").count() === 1, "Editor lacks Export Bundle");
    assert(await page.locator(".focus-panel").count() >= 1, "Editor lacks focused inspector panel");
    assert(await page.locator(".advanced-inspector").count() >= 1, "Editor lacks full-control inspector details");
    assert(await page.locator('.queue-switch [data-queue-mode="selected"].is-active').count() === 1, "Editor did not open the Edit Set");

    const activeRef = await page.locator(".finding-card.is-active").getAttribute("data-ref");
    assert(activeRef, "Editor did not activate a finding");
    const slideLabel = await page.locator("#slideLabel").textContent();
    const slideMatch = /\((\d+)\/(\d+)\)/.exec(slideLabel || "");
    if (slideMatch && Number(slideMatch[2]) > 1) {
      const forward = Number(slideMatch[1]) < Number(slideMatch[2]);
      await page.locator(forward ? "#nextSlide" : "#prevSlide").click();
      await page.waitForTimeout(100);
      assert(await page.locator(".callout").count() === 0, "Callout followed slide navigation without an explicit move");
      assert(await page.locator('[data-workflow="move-callout-here"]:visible').count() >= 1, "Cross-screenshot callout move action is missing");
      await page.locator(forward ? "#prevSlide" : "#nextSlide").click();
      await page.waitForTimeout(100);
      assert(await page.locator(".callout").count() >= 1, "Callout did not return on its home screenshot");
    }

    await page.locator("#previewToggle").click();
    const hudText = await page.locator(".stage-hud span").textContent();
    assert(/AI Draft View/i.test(hudText || ""), "Preview toggle did not switch to AI Draft View");
    await page.locator("#previewToggle").click();
    assert(await page.locator(".connector-line").count() <= 1, "Editor rendered multiple callout connector lines for one active finding");

    await page.locator('[data-style-preset="glow"]').first().click();
    assert(await page.locator(".marker-glow").count() >= 1, "Glow style did not render a glow halo");
    const glowAnimation = await page.locator(".marker-glow").first().evaluate(el => getComputedStyle(el).animationName);
    assert(glowAnimation && glowAnimation !== "none", "Glow halo is not animated");

    await page.locator('[data-callout-color-preset="low"]').first().click();
    const calloutBorder = await page.locator(".callout").first().evaluate(el => getComputedStyle(el).borderColor);
    assert(calloutBorder && calloutBorder !== "rgba(0, 0, 0, 0)", "Callout color control did not update the callout color");

    await page.locator("#previewFinding").click();
    assert(await page.locator("#previewModal:not([hidden])").count() === 1, "Preview Finding did not open the in-editor preview modal");
    await page.locator("#closePreview").click();

    await page.keyboard.press("Delete");
    await page.waitForTimeout(100);
    assert(await page.getByText("not placed").count() >= 1, "Delete did not clear the hotspot independently");

    await page.locator('[data-tool="dim"]').click();
    const layer = page.locator(".marker-layer");
    const box = await layer.boundingBox();
    assert(box, "Marker layer has no bounding box");
    await page.mouse.move(box.x + box.width * 0.25, box.y + box.height * 0.25);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.45);
    await page.mouse.up();
    assert(await page.locator(".dim-region").count() >= 1, "Dim Region tool did not create a shaped dim effect");

    console.log(JSON.stringify({ ok: true, fixture: fixtureArg, device, fid, activeRef }, null, 2));
  } finally {
    if (browser) await browser.close();
    await rm(tmpRoot, { recursive: true, force: true });
  }
}

function cssEscape(value) {
  if (globalThis.CSS?.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

main().catch(error => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
