const {chromium}=require('playwright-core'), assert=require('assert');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
 const p=await b.newPage({viewport:{width:1280,height:800}});
 await p.route('**/env.js',r=>r.fulfill({status:200,contentType:'text/javascript',body:"window.env={API_URL:'/api'}"}));
 await p.route('**/api/**',r=>{const x=new URL(r.request().url()).pathname;if(x.endsWith('/me'))return r.fulfill({status:401,contentType:'application/json',body:'{}'});if(x.endsWith('/login'))return r.fulfill({status:200,contentType:'application/json',body:'{"email":"test@example.com"}'});return r.fulfill({status:404,body:'{}'})});
 await p.goto('http://127.0.0.1:18205/login.html');
 await p.waitForSelector('.recovery-warning:visible');
 assert(await p.locator('.recovery-warning').isVisible());assert.equal(await p.getByText('Forgot password?').count(),0);
 await p.screenshot({path:'/downloads/cn-no-recovery-login-local.png'});
 await p.locator('[data-show="register-form"]').click();assert(!(await p.locator('.recovery-warning').isVisible()));assert(await p.locator('.signup-password-hint').isVisible());await p.screenshot({path:'/downloads/cn-signup-password-hint-local.png'});
 await p.locator('[data-show="login-form"]').click();
 await p.locator('#login-email').fill('test@example.com');await p.locator('#login-password').fill('correct-password');await p.locator('#login-button').click();
 await p.waitForURL(/index.html/);await b.close(); console.log('login form warning only, mocked sign-in navigation passed');
})().catch(e=>{console.error(e);process.exit(1)});
