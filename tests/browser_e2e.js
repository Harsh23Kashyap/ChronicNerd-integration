const { chromium } = require('playwright-core');
const fs = require('fs');
const assert = require('assert');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox']});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const email = `browser-e2e-${Date.now()}@example.com`;
  const password = 'browser-test-password';
  const log = [];
  page.on('console', msg => log.push('console: ' + msg.text()));
  page.on('pageerror', err => log.push('pageerror: ' + err.message));

  await page.goto('http://localhost:18080/index.html');
  await page.waitForURL('**/login.html', {waitUntil: 'domcontentloaded'});  // no session yet
  await page.click('[data-show="register-form"]');
  await page.fill('#register-email', email);
  await page.fill('#register-password', password);
  await page.fill('#register-confirm', 'not the same');
  await page.click('#register-button');
  assert.match(await page.textContent('#register-error'), /do not match/);
  await page.fill('#register-confirm', password);
  await page.click('#register-button');
  await page.waitForURL('**/index.html', {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => document.getElementById('account-email').textContent.includes('@'));
  assert.equal(await page.textContent('#account-email'), email);
  const cookies = await page.context().cookies();
  const session = cookies.find(c => c.name === 'dietnerd_session');
  assert(session && session.httpOnly, 'session cookie must be HttpOnly');

  await page.fill('#question', 'browser cached question');
  await page.click('#submit');
  await page.waitForFunction(() => document.querySelector('#chat-thread').textContent.includes('Cached browser-test answer'));
  const firstConversation = await page.evaluate(() => sessionStorage.getItem('dietnerd_conversation_id'));
  assert(firstConversation);
  assert.equal(await page.locator('.chat-message.user').count(), 1);
  assert.equal(await page.locator('.chat-message.assistant').count(), 1);

  // A follow-up inside a conversation is answered directly, using earlier turns.
  await page.fill('#question', 'what about sleep?');
  await page.click('#submit');
  await page.waitForFunction(() => document.querySelector('#chat-thread').textContent.includes('magnesium on sleep'));
  assert.equal(await page.locator('.chat-message.user').count(), 2);
  assert.equal(await page.locator('.chat-message.assistant').count(), 2);

  await page.click('#new-conversation');
  assert.equal(await page.evaluate(() => sessionStorage.getItem('dietnerd_conversation_id')), null);
  await page.fill('#question', 'fresh conversation question');
  await page.click('#submit');
  await page.waitForSelector('#similarQuestions button:last-child');
  await page.click('#similarQuestions button:last-child');
  await page.waitForFunction(() => document.querySelector('#chat-thread').textContent.includes('answer for: fresh conversation question'));
  const secondConversation = await page.evaluate(() => sessionStorage.getItem('dietnerd_conversation_id'));
  assert(secondConversation && secondConversation !== firstConversation);

  await page.selectOption('#conversation-select', firstConversation);
  await page.waitForFunction(() => document.querySelector('#chat-thread').textContent.includes('magnesium on sleep'));
  await page.selectOption('#conversation-select', secondConversation);
  await page.waitForFunction(() => document.querySelector('#chat-thread').textContent.includes('fresh conversation question'));

  fs.writeFileSync('tests/browser-upload.txt', 'Browser upload nutrition facts');
  await page.setInputFiles('#attachment-file', 'tests/browser-upload.txt');
  await page.waitForFunction(() => document.querySelector('#existing-attachments').textContent.includes('browser-upload.txt'));
  await page.fill('#question', 'summarize my upload');
  await page.click('#submit');
  await page.waitForFunction(() => document.querySelector('#chat-thread').textContent.includes('answer for: summarize my upload'));
  await page.click('[data-filename="browser-upload.txt"]');
  await page.waitForFunction(() => !document.querySelector('#existing-attachments').textContent.includes('browser-upload.txt'));

  await page.screenshot({path: '/downloads/chronicnerd-browser-answer.png', fullPage: true});

  page.once('dialog', dialog => dialog.accept());
  await page.click('#delete-conversation');
  await page.waitForFunction(() => sessionStorage.getItem('dietnerd_conversation_id') === null);
  await page.waitForFunction(id => !document.querySelector(`#conversation-select option[value="${id}"]`), secondConversation);

  await page.screenshot({path: '/downloads/chronicnerd-browser-final.png', fullPage: true});

  // Sign out, then reset the password through the emailed link.
  await page.click('#account-button');
  await page.click('#logout-link');
  await page.waitForURL('**/login.html', {waitUntil: 'domcontentloaded'});
  await page.goto('http://localhost:18080/index.html');
  await page.waitForURL('**/login.html', {waitUntil: 'domcontentloaded'});
  await page.click('[data-show="forgot-form"]');
  await page.fill('#forgot-email', email);
  await page.click('#forgot-button');
  await page.waitForSelector('#forgot-success:not(:empty)');
  await page.screenshot({path: '/downloads/chronicnerd-forgot-sent.png'});
  const resetUrl = fs.readFileSync('tests/.last-reset-url', 'utf8');
  fs.unlinkSync('tests/.last-reset-url');
  await page.goto(resetUrl);
  await page.waitForSelector('#reset-form:not([hidden])');
  await page.fill('#reset-password', 'a brand new password');
  await page.fill('#reset-confirm', 'a brand new password');
  await page.screenshot({path: '/downloads/chronicnerd-reset-form.png'});
  await page.click('#reset-button');
  await page.waitForSelector('#login-info:not(:empty)');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('#login-button');
  await page.waitForSelector('#login-error:not(:empty)');
  assert.match(await page.textContent('#login-error'), /Incorrect email or password/);
  await page.fill('#login-password', 'a brand new password');
  await page.click('#login-button');
  await page.waitForURL('**/index.html', {waitUntil: 'domcontentloaded'});
  fs.unlinkSync('tests/browser-upload.txt');
  assert.equal(log.filter(line => line.startsWith('pageerror:')).length, 0, log.join('\n'));
  console.log(JSON.stringify({status: 'passed', firstConversation, secondConversation, browser: await browser.version(), consoleEvents: log.length}));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
