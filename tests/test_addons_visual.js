const {chromium} = require('playwright-core');
const assert = require('assert');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
  const page = await browser.newPage({viewport:{width:1360,height:850}});
  const errors=[]; page.on('pageerror', e=>errors.push(e.message));
  await page.route('**/me', r=>r.fulfill({status:200,contentType:'application/json',body:'{"email":"visual-test@example.invalid"}'}));
  await page.route('**/conversations', r=>r.fulfill({status:200,contentType:'application/json',body:'{"conversations":[]}'}));
  await page.goto('http://127.0.0.1:18181/addons.html');
  await page.waitForSelector('body:not(.auth-pending)');
  assert.equal(await page.locator('.addon-list .addon').count(),1);
  assert.equal(await page.locator('.roadmap-grid article').count(),4);
  assert.equal(await page.locator('#toggle-ledger').isChecked(),false);
  await page.screenshot({path:'/downloads/chronicnerd-addons-overview.png',fullPage:true});
  await page.locator('#toggle-ledger').check();
  await page.reload();
  assert.equal(await page.locator('#toggle-ledger').isChecked(),true);
  await page.goto('http://127.0.0.1:18181/index.html');
  await page.waitForFunction(() => !document.documentElement.classList.contains('auth-pending'));
  await page.evaluate(() => showAssistantAnswer('What we know\nA result [1].\n\nWhat we don\'t know\nUncertain.\n\nWhat to ask a dietitian\nDoes it apply?', [
    {claim:'A result [1].',citation_marker:'[1]',source_title:'Sample Study',source_url:'https://pubmed.ncbi.nlm.nih.gov/123/',evidence_note:'Support not verified.'}
  ], 'What does the research say?'));
  assert.equal(await page.locator('.evidence-ledger').count(),1);
  assert.equal(await page.locator('.addon-save-button,#sidebar-notebook').count(),0);
  await page.goto('http://127.0.0.1:18181/addons.html');


  await page.reload();
  assert.equal(await page.locator('#toggle-notebook,#notebook-section').count(),0);
  // Settings remain isolated by signed-in account, not just origin.
  await page.evaluate(() => sessionStorage.setItem('dietnerd_user','other@example.invalid'));
  assert.equal(await page.evaluate(() => ChronicNerdAddons.enabled('ledger')), false);
  await page.evaluate(() => sessionStorage.setItem('dietnerd_user','visual-test@example.invalid'));

  await page.locator('#toggle-ledger').uncheck();
  await page.goto('http://127.0.0.1:18181/index.html');
  await page.waitForFunction(() => !document.documentElement.classList.contains('auth-pending'));
  await page.evaluate(() => showAssistantAnswer('What we know\nA result [1].', [
    {claim:'A result [1].',citation_marker:'[1]',source_title:'Sample Study'}
  ], 'Another question'));
  assert.equal(await page.locator('.evidence-ledger').count(),0);
  assert.equal(await page.locator('.addon-save-button').count(),0);
  await page.setViewportSize({width:390,height:844});
  await page.goto('http://127.0.0.1:18181/addons.html');
  await page.waitForFunction(() => !document.documentElement.classList.contains('auth-pending'));
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
  await page.screenshot({path:'/downloads/chronicnerd-addons-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',url:page.url(),roadmap:4,errors}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
