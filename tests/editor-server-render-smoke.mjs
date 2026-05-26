import { spawn } from "node:child_process";
import { mkdtemp, rm, cp, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixtureArg = process.argv[2] || "tests/fixtures/2026-05-03-awdmods-pdp";
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

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForServer(port) {
  for (let i = 0; i < 60; i++) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/editor.html`);
      if (response.ok) return;
    } catch {
      // keep polling
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error("editor server did not become ready");
}

async function main() {
  assert(await exists(sourceEngagement), `Missing smoke fixture: ${sourceEngagement}`);
  const tmpRoot = await mkdtemp(path.join(tmpdir(), "ecp-editor-server-"));
  const tmpEngagement = path.join(tmpRoot, path.basename(sourceEngagement));
  const port = 8807;
  let browser;
  let server;
  try {
    await cp(sourceEngagement, tmpEngagement, { recursive: true });
    server = spawn("node", [
      "scripts/serve-editor.cjs",
      "--engagement",
      tmpEngagement,
      "--port",
      String(port),
    ], { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] });
    await waitForServer(port);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    await page.goto(`http://127.0.0.1:${port}/editor.html#device=${encodeURIComponent(device)}`);
    await page.waitForSelector("#stage .stage-hud", { timeout: 15000 });
    await page.locator("#exportFinal").click();
    await page.waitForTimeout(1000);

    const finalName = `visual-report-${device}-final.html`;
    assert(await exists(path.join(tmpEngagement, finalName)), `Final report was not rendered: ${finalName}`);
    const finalResponse = await fetch(`http://127.0.0.1:${port}/${finalName}`);
    assert(finalResponse.ok, "Final report was not served");
    const finalHtml = await finalResponse.text();
    assert(finalHtml.includes('class="app-header"'), "Final report did not preserve the original audit app shell");
    assert(finalHtml.includes("detail-source"), "Final report is missing original source/evidence detail sections");
    assert(!finalHtml.includes("Human-reviewed ECP audit"), "Final report used the standalone review-state template");

    console.log(JSON.stringify({ ok: true, fixture: fixtureArg, device, finalName }, null, 2));
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
    await rm(tmpRoot, { recursive: true, force: true });
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
