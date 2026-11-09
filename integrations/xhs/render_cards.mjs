// Facet Studio Xiaohongshu card renderer (P2).
// Usage: node render_cards.mjs <spec.json>
// Spec: { out_dir, brand, kicker, cover_text, title, cards: [{kind,image,caption,index,total}] }
// Requires Playwright. By default it resolves from the local LibreChat clone;
// override with FACET_STUDIO_PLAYWRIGHT=/path/to/playwright.

import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';

const require = createRequire(import.meta.url);
let playwright;
try {
  // Prefer a locally installed playwright.
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
const { chromium } = playwright;

const specPath = process.argv[2];
if (!specPath) {
  console.error('usage: node render_cards.mjs <spec.json>');
  process.exit(2);
}
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const outDir = spec.out_dir;
fs.mkdirSync(outDir, { recursive: true });

const W = 1080;
const H = 1440;
const FONT_SERIF = '"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif';
const FONT_SANS = 'system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif';

function esc(s = '') {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function dataUri(file) {
  if (!file || !fs.existsSync(file)) return '';
  const ext = path.extname(file).toLowerCase();
  const mime = ext === '.png' ? 'image/png' : 'image/jpeg';
  return `data:${mime};base64,${fs.readFileSync(file).toString('base64')}`;
}

function pageHtml(inner) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
*{box-sizing:border-box}html,body{margin:0;width:${W}px;height:${H}px;overflow:hidden}
body{background:#f4f3ee;color:#191817;font-family:${FONT_SANS}}
.page{position:relative;width:${W}px;height:${H}px;padding:64px 64px 56px;display:flex;flex-direction:column;background:#f4f3ee}
.brand{font-size:28px;letter-spacing:.18em;color:#8a847a;font-weight:700}
.kicker{display:inline-flex;align-self:flex-start;margin-top:28px;padding:10px 20px;border:1px solid #d8d3c8;
border-radius:999px;font-size:26px;color:#5a554e;background:#eeede6}
.title{font-family:${FONT_SERIF};font-weight:600;font-size:96px;line-height:1.12;letter-spacing:-.01em;margin:44px 0 0;word-break:keep-all;overflow-wrap:break-word;text-wrap:balance}
.title.small{font-size:76px}
.sub{font-size:38px;line-height:1.55;color:#5a554e;margin-top:28px;max-width:860px}
.hero{margin-top:auto;border-radius:28px;overflow:hidden;border:1px solid #d8d3c8;background:#191817;
padding:18px;height:560px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.hero img{max-width:100%;max-height:calc(100% - 42px);width:auto;height:auto;object-fit:contain;display:block;border-radius:14px}
.hero .cap{padding:12px 6px 2px;font-size:24px;color:#e8e2d6;text-align:center}
.footer{display:flex;justify-content:space-between;align-items:center;margin-top:30px;font-size:26px;color:#8a847a}
.accent{width:120px;height:8px;background:#c96442;border-radius:999px;margin-top:34px}
.text-cover .cover-main{margin-top:auto;margin-bottom:auto;width:100%}
.card-top{display:flex;justify-content:space-between;align-items:center}
.card-index{font-size:24px;letter-spacing:.14em;color:#8a847a}
.card-media{flex:0 0 620px;height:620px;margin:24px 0 22px;background:#fff;border:1px solid #d8d3c8;border-radius:24px;padding:24px;
display:flex;align-items:center;justify-content:center;overflow:hidden}
.card-media img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;display:block;border-radius:12px}
.placeholder{font-size:30px;color:#8a847a}
.card-cap{font-family:${FONT_SERIF};font-size:40px;line-height:1.4;color:#191817;flex:1;display:flex;align-items:center}
.card-foot{display:flex;justify-content:space-between;align-items:center;padding-top:18px;font-size:22px;color:#8a847a}
</style></head><body>${inner}</body></html>`;
}

function coverHtml(card) {
  const rawTitle = card.title || spec.cover_text || spec.title || '';
  const long = Array.from(rawTitle).length > 25;
  const img = dataUri(card.image);
  const head = `
    <div class="brand">${esc(spec.brand || 'FACET STUDIO')}</div>
    <div class="kicker">${esc(spec.kicker || '笔记')}</div>
    <div class="title ${long ? 'small' : ''}">${esc(rawTitle)}</div>
    ${card.subtitle ? `<div class="sub">${esc(card.subtitle)}</div>` : ''}`;
  const footer = card.index || card.footer ? `<div class="footer"><span></span><span>${esc(card.index || card.footer || '')}</span></div>` : '';
  if (!img) {
    return pageHtml(`<div class="page text-cover">
      <div class="cover-main">${head}<div class="accent"></div></div>
      ${footer}
    </div>`);
  }
  return pageHtml(`<div class="page">
    ${head}
    <div class="hero"><img src="${img}"><div class="cap">${esc(card.caption || '')}</div></div>
    ${footer}
  </div>`);
}

function imageCardHtml(card) {
  const img = dataUri(card.image);
  const caption = card.caption || '';
  return pageHtml(`<div class="page">
    <div class="card-top"><div class="brand">${esc(spec.brand || 'FACET STUDIO')}</div><div class="card-index">${esc(card.index || '')}</div></div>
    <div class="card-media">${img ? `<img src="${img}">` : '<div class="placeholder">无配图</div>'}</div>
    ${caption ? `<div class="card-cap">${esc(caption)}</div>` : ''}
    <div class="card-foot"><span>${esc(spec.brand || 'FACET STUDIO')}</span><span>${esc(spec.kicker || '笔记')}</span></div>
  </div>`);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  let n = 0;
  for (const card of spec.cards || []) {
    n += 1;
    const html = card.kind === 'cover' ? coverHtml(card) : imageCardHtml(card);
    await page.setContent(html, { waitUntil: 'load' });
    await page.waitForTimeout(120);
    const file = path.join(outDir, `${String(n).padStart(2, '0')}_${card.kind === 'cover' ? 'cover' : 'card'}.png`);
    await page.screenshot({ path: file });
    console.log(file);
  }
  await browser.close();
})().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
