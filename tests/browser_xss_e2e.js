const { chromium } = require('playwright-core');
const fs = require('fs');
const assert = require('assert');
const path = require('path');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1280, height: 900}});
  const appScript = fs.readFileSync(path.join(__dirname, '../dietnerd-website/index.js'), 'utf8');
  const malicious = '<img src=x onerror="window.__xss=(window.__xss||0)+1">.pdf';
  await page.route('**/*', async route => {
    if (route.request().resourceType() === 'document') {
      await route.fulfill({contentType: 'text/html', body: `<!doctype html><html><body>
        <div id="existing-attachments"></div><span id="attachment-label"></span>
        <script>window.env={API_URL:'http://test'};sessionStorage.setItem('dietnerd_user','x@example.com');window.__xss=0;window.fetch=async()=>({ok:true,json:async()=>({documents:[${JSON.stringify(malicious)}]})});</script>
        <script>${appScript}</script></body></html>`});
    } else await route.abort();
  });
  await page.goto('http://test/index.html');
  await page.evaluate(async () => { await refreshExistingAttachments(); });
  assert.equal(await page.evaluate(() => window.__xss), 0);
  assert.equal(await page.locator('#existing-attachments img').count(), 0);
  assert.equal(await page.textContent('#existing-attachments'), malicious + '\u2715');
  assert.equal(await page.getAttribute('.existing-attachment-remove', 'data-filename'), malicious);

  await page.evaluate(() => {
    document.body.insertAdjacentHTML('beforeend', '<div id="answer-proof"></div>');
    document.querySelector('#answer-proof').innerHTML = formatText('<img src=x onerror="window.__xss+=1"> **supported**');
  });
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(() => window.__xss), 0);
  assert.equal(await page.locator('#answer-proof img').count(), 0);
  assert.equal(await page.locator('#answer-proof strong').textContent(), 'supported');
  await page.screenshot({path: '/downloads/chronicnerd-xss-after.png', fullPage: true});
  console.log(JSON.stringify({status:'passed', rendered:await page.textContent('#existing-attachments')}));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
