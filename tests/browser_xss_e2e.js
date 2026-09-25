const { chromium } = require('playwright-core');
const fs = require('fs');
const assert = require('assert');
const path = require('path');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1280, height: 900}});
  const apiScript = fs.readFileSync(path.join(__dirname, '../dietnerd-website/api.js'), 'utf8');
  const appScript = fs.readFileSync(path.join(__dirname, '../dietnerd-website/index.js'), 'utf8');
  const malicious = '<img src=x onerror="window.__xss=(window.__xss||0)+1">.pdf';
  await page.route('**/*', async route => {
    if (route.request().resourceType() === 'document') {
      await route.fulfill({contentType: 'text/html', body: `<!doctype html><html><body>
        <div id="existing-attachments"></div><span id="attachment-label"></span>
        <script>window.env={API_URL:'http://test'};sessionStorage.setItem('dietnerd_user','x@example.com');window.__xss=0;window.fetch=async()=>({ok:true,json:async()=>({documents:[${JSON.stringify(malicious)}]})});</script>
        <script>${apiScript}</script>
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

  // Citation text comes from PubMed metadata and must be escaped in the sources list.
  const refs = await page.evaluate(() => {
    const evil = '<img src=x onerror="window.__xss+=1">';
    localStorage.setItem('citations', JSON.stringify([`[1] ${evil} Author A. ${evil} Title. ${evil} Journal. 2024.`]));
    localStorage.setItem('referenceObject', JSON.stringify({[`[1] ${evil} Author A. ${evil} Title. ${evil} Journal. 2024.`]: {PMCID: 'None'}}));
    document.body.insertAdjacentHTML('beforeend', '<div id="refs-proof"></div>');
    const html = formatReferences('Answer text [1].\n\nReferences:\n[1] ' + evil + ' Author A. Title. Journal. 2024.');
    document.querySelector('#refs-proof').innerHTML = html;
    return html;
  });
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(() => window.__xss), 0);
  assert.equal(await page.locator('#refs-proof img[onerror], #refs-proof img[src="x"]').count(), 0, refs);
  assert.ok(await page.locator('#refs-proof a').count() >= 1, 'reference link should render: ' + refs);
  await page.screenshot({path: '/downloads/chronicnerd-xss-after.png', fullPage: true});
  console.log(JSON.stringify({status:'passed', rendered:await page.textContent('#existing-attachments')}));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
