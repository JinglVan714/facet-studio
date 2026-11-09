// Facet Studio PDF helper: render SVG figures to PNG for XeLaTeX.
// Usage: node render_svg_png.mjs <spec.json>
// Spec: { items: [{ svg, png }] }
// Requires Playwright. By default resolves from the local node_modules;
// override with FACET_STUDIO_PLAYWRIGHT=/path/to/playwright.

import { createRequire } from 'module';
import fs from 'fs';

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require('playwright');
} catch {
  const fallback = process.env.FACET_STUDIO_PLAYWRIGHT;
  if (!fallback) {
    console.error(
      'playwright not found. Install it (npm i playwright) or set ' +
        'FACET_STUDIO_PLAYWRIGHT to a playwright module directory.'
    );
    process.exit(2);
  }
  playwright = require(fallback);
}

const specPath = process.argv[2];
if (!specPath) {
  console.error('usage: node render_svg_png.mjs <spec.json>');
  process.exit(2);
}
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const items = spec.items || [];

const { chromium } = playwright;
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});
for (const item of items) {
  const svg = fs.readFileSync(item.svg, 'utf8');
  await page.setContent(
    '<!doctype html><html><head><style>' +
      'html,body{margin:0;padding:0;background:#fff}' +
      '#fig{width:1440px}' +
      '#fig svg{width:100%;height:auto;display:block}' +
      '</style></head><body><div id="fig">' +
      svg +
      '</div></body></html>'
  );
  const element = await page.$('#fig svg');
  if (!element) {
    console.error(`svg not found in ${item.svg}`);
    process.exit(3);
  }
  await element.screenshot({ path: item.png });
}
await browser.close();
