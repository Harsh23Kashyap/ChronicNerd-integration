const {chromium} = require('playwright-core');
const assert = require('assert');
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
  const page = await browser.newPage({viewport:{width:1360,height:850}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/me',r=>r.fulfill({status:200,contentType:'application/json',body:'{"email":"local-test@example.invalid"}'}));
  await page.route('**/conversations',r=>r.fulfill({status:200,contentType:'application/json',body:'{"conversations":[]}'}));
  await page.goto('http://127.0.0.1:18181/index.html',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.documentElement.classList.contains('auth-pending'));
  await page.evaluate(()=>showAssistantAnswer('What we know\nThe outcome was reported in this trial [1].\n\nWhat we don\'t know\nThe population match is unclear.\n\nWhat to ask a dietitian\nIs this applicable to me?\n\nReferences:\n[1] A Author. Nutrition Study. Journal.', [
    {claim:'The outcome was reported in this trial [1].',citation_marker:'[1]',source_title:'Nutrition Study',source_url:'https://pubmed.ncbi.nlm.nih.gov/123/',support_status:'not independently verified',evidence_note:'Source matched by title; passage and support not verified.'}
  ]));
  await page.locator('.evidence-ledger summary').click();
  assert.match(await page.locator('.evidence-ledger').innerText(),/not verified/);
  assert.equal(await page.locator('.evidence-ledger a').getAttribute('href'),'https://pubmed.ncbi.nlm.nih.gov/123/');
  await page.locator('.evidence-ledger-entry').scrollIntoViewIfNeeded();
  await page.screenshot({path:'/downloads/chronicnerd-evidence-ledger.png',fullPage:true});
  assert.deepEqual(errors,[]); console.log(JSON.stringify({url:page.url(),errors,ledgerVisible:await page.locator('.evidence-ledger-entry').isVisible()}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
