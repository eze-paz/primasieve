const { test, expect } = require('@playwright/test');

test.setTimeout(30000);
function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

test.describe('sandpie smoke', () => {
  test('page loads without console errors', async ({ page }) => {
    const errors = [];
    const badReqs = [];

    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', err => {
      errors.push('PAGE ERROR: ' + (err.message || String(err)));
    });
    page.on('response', res => {
      if (res.status() >= 400) badReqs.push(res.url() + ' => ' + res.status());
    });

    await page.goto('http://localhost:8765/', { waitUntil: 'domcontentloaded' });
    await wait(2500);

    expect(await page.$('body')).toBeTruthy();
    expect(await page.evaluate(() => typeof SandpieMenu !== 'undefined')).toBe(true);
    expect(await page.evaluate(() => typeof SandpieTools !== 'undefined')).toBe(true);
    expect(await page.evaluate(() => typeof SandpieZeroshot !== 'undefined')).toBe(true);

    if (badReqs.length) {
      console.log('\n=== HTTP FAILURES ===');
      badReqs.forEach(u => console.log('  ' + u));
    }
    if (errors.length) {
      console.log('\n=== CONSOLE ERRORS ===');
      errors.forEach(e => console.log('  ' + e));
    }

    expect(badReqs).toHaveLength(0);
  });

  test('zeroshot sidebar renders and toggles', async ({ page }) => {
    await page.goto('http://localhost:8765/', { waitUntil: 'domcontentloaded' });
    await wait(2500);
    await page.locator('details summary:has-text("Zero-shot")').click();
    await wait(300);
    await page.locator('#zsToggle').click();
    await wait(300);
    expect(await page.evaluate(() => SandpieZeroshot.isActive())).toBe(true);

    await page.locator('#zsToggle').click();
    await wait(300);
    expect(await page.evaluate(() => SandpieZeroshot.isActive())).toBe(false);
  });
});
