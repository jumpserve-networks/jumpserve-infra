// Fixed production read-only browser smoke check. No login or mutation calls.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
const require=createRequire(new URL('../../jumpserve-front-end/package.json',import.meta.url));
const {chromium}=require('playwright');
assert.equal(process.argv.length,2,'Fixed production target only.');
const site='https://jumpserve.quaint-lab.org',revision='8c00fd642dd6b1f898e77b16c94b8d5241375a21';
const api='https://d3o7xdethb.execute-api.us-east-1.amazonaws.com';
const out='.test-artifacts/assessment-ui-production/'+new Date().toISOString().replaceAll(':','-');await mkdir(out,{recursive:true});
const checks=[],errors=[],methods=[];let browser;
async function check(name,fn){await fn();checks.push(name);console.log('PASS '+name);}
try{
 const identity=await (await fetch(site+'/api/platform-version',{cache:'no-store'})).json();assert.equal(identity.revision,revision);
 browser=await chromium.launch({headless:true,executablePath:existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':undefined});
 const context=await browser.newContext({viewport:{width:1365,height:900}});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(![site,api,'https://regphejnlvfpyokpniny.supabase.co'].includes(url.origin))return route.abort();methods.push(route.request().method());return route.continue();});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(20000);
 const path='/research-verification/assessments';let title,assessment;
 await check('production cards and table open the same recorded assessments',async()=>{
  await page.goto(site+path);const first=page.locator('article[data-paper-id]').first();await first.waitFor();title=await first.locator('h2 a').innerText();assessment=await first.locator('h2 a').getAttribute('href');assert.match(assessment,/^\/research-verification\/assessment\/[a-f0-9-]+$/);
  await page.getByRole('navigation',{name:'Assessment view',exact:true}).getByRole('button',{name:'Table',exact:true}).click();const table=page.getByRole('table',{name:'Assessments',exact:true});await table.getByRole('link',{name:title,exact:true}).waitFor();assert.equal(await table.getByRole('link',{name:title,exact:true}).getAttribute('href'),assessment);await page.screenshot({path:out+'/table-desktop.png',fullPage:true});
 });
 await check('production name filter retains the selected table view',async()=>{
  await page.getByLabel('Filter by name',{exact:true}).fill(title.slice(0,128));await page.getByRole('button',{name:'Filter',exact:true}).click();await page.waitForURL(url=>url.searchParams.has('name'));await page.getByRole('table',{name:'Assessments',exact:true}).getByRole('link',{name:title,exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('view'),'table');
 });
 await check('ready paper overview links to claim selection with exact sign-in return',async()=>{
  await page.goto(site+assessment);await page.getByTestId('assessment-detail').waitFor();await page.locator('[data-assessment-stage]').filter({hasNotText:'Loading…'}).waitFor();
  const detail=await (await fetch(api+'/research/papers/'+assessment.split('/').at(-1))).json();assert.equal(detail.version,'research-paper-detail-v1');
  if(detail.preparation_status==='ready'){
   const choose=page.getByRole('button',{name:'Choose central claims and testable findings',exact:true});await choose.waitFor();const review='/research-verification/new-assessment/'+detail.paper.id;assert.equal(await choose.getAttribute('href'),review);await page.screenshot({path:out+'/review-ready.png',fullPage:true});await choose.click();await page.waitForURL(url=>url.pathname==='/login');assert.equal(new URL(page.url()).searchParams.get('next'),review);
  }else assert.equal(await page.getByRole('button',{name:'Choose central claims and testable findings',exact:true}).count(),0);
 });
 await check('prompts stay in the header and Platform Updates is in desktop/mobile navigation',async()=>{
  await page.goto(site+path);assert.equal(await page.locator('header').getByRole('link',{name:'Platform updates',exact:true}).count(),0);assert.equal(await page.locator('[data-slot="module-sidebar"]').getByRole('link',{name:'Platform Updates',exact:true}).getAttribute('href'),'/platform-updates');await page.locator('header').getByRole('link',{name:'Prompts',exact:true}).click();await page.waitForURL(url=>url.pathname==='/login'&&url.searchParams.get('next')==='/prompts');
  await page.setViewportSize({width:390,height:844});await page.goto(site+path+'?view=table');await page.getByRole('table',{name:'Assessments',exact:true}).waitFor();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:out+'/table-mobile.png',fullPage:true});await page.getByRole('button',{name:'Open module menu',exact:true}).click();await page.getByRole('dialog').getByRole('link',{name:'Platform Updates',exact:true}).click();await page.waitForURL(url=>url.pathname==='/login'&&url.searchParams.get('next')==='/platform-updates');assert.equal(await page.getByRole('dialog').count(),0);
 });
 assert.deepEqual(errors,[]);assert.ok(methods.every(method=>['GET','HEAD','OPTIONS'].includes(method)));
}catch(error){process.exitCode=1;errors.push(error.stack);if(browser){const page=browser.contexts()[0]?.pages()[0];if(page)await page.screenshot({path:out+'/failure.png',fullPage:true});}}
finally{if(browser)await browser.close();await writeFile(out+'/report.json',JSON.stringify({passed:checks.length===4&&errors.length===0,revision,checks,errors,request_methods:[...new Set(methods)],production_writes:0,google_login_exercised:false},null,2)+'\n');console.log(JSON.stringify({out,checks:checks.length,errors}));}
