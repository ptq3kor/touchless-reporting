import { chromium } from 'playwright';

const browser = await chromium.launch();
const errors = [];
for (const [name, vp] of [['dash-1920', { width: 1920, height: 1080 }], ['dash-1366', { width: 1366, height: 768 }]]) {
  const page = await browser.newPage({ viewport: vp });
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `/tmp/${name}.png`, fullPage: true });
  await page.close();
}
// interaction pass: click BBM tab, check TNS updates
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', (e) => errors.push(String(e)));
await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
await page.click('text=BBM Mobility Solutions');
await page.waitForTimeout(1200);
const body = await page.textContent('body');
console.log('BBM TNS 4,974.5 visible:', body.includes('4,974.5'));
await page.screenshot({ path: '/tmp/dash-bbm.png', fullPage: true });
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
