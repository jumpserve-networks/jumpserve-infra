import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire(new URL('../../jumpserve-front-end/package.json',import.meta.url));
const {chromium}=require('playwright');
const origin='https://jumpserve.quaint-lab.org',api='https://d3o7xdethb.execute-api.us-east-1.amazonaws.com';
const directory='.test-artifacts/builder-production-browser/'+new Date().toISOString().replaceAll(':','-');await mkdir(directory,{recursive:true});
const report={started_at:new Date().toISOString(),origin,checks:[],errors:[],conditional_gaps:['Authenticated upload/confirmation and actual authenticated builder execution require a legitimate browser session; this isolated browser has none.','Generated-package activation remains subject to separate native-answer, cloud lifecycle and cost-policy gates.'],reviewer:{identity:'Primary Codex AI implementer',type:'AI',independent:false},measured_charges_usd:null};
let browser;
async function check(name,fn){try{const evidence=await fn();report.checks.push({name,passed:true,evidence});}catch(e){report.checks.push({name,passed:false,reason:e.message});report.errors.push(e.message);}}
try{
 browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1365,height:900},timezoneId:'America/Chicago'});const page=await context.newPage();page.setDefaultTimeout(20000);
 const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
 await check('Public paper catalog and live queue',async()=>{
  const response=await fetch(api+'/research/papers?bibliography=1&initiator=1');assert.equal(response.status,200);const catalog=await response.json();assert.equal(catalog.version,'research-paper-catalog-v1');assert.equal(catalog.coverage.papers,catalog.papers.length);
  await page.goto(origin+'/research-verification/previous-assessments',{waitUntil:'networkidle'});await page.getByRole('heading',{name:'Previous Assessments',exact:true}).waitFor();
  assert.equal(await page.locator('article[data-paper-id]').count(),catalog.papers.length);assert.equal(await page.getByRole('link',{name:'View experiment queue',exact:true}).count(),0);
  if(catalog.papers.length){const paper=catalog.papers[0];await page.goto(origin+'/research-verification/experiment-queue?assessment='+paper.id,{waitUntil:'networkidle'});assert.ok(!(await page.locator('main').innerText()).includes('Failed to fetch'));assert.ok((await page.locator('main').innerText()).includes(paper.title??''));}
  return {papers:catalog.papers.length,queue:'Public assessment route loaded; no credentials used'};
 });
 await check('Desktop/mobile theme, layout and navigation',async()=>{
  for(const width of [1365,390]){await page.setViewportSize({width,height:900});for(const theme of ['Light Mode','Dark Mode']){
   await page.goto(origin+'/research-verification/previous-assessments',{waitUntil:'networkidle'});await page.getByRole('button',{name:theme,exact:true}).click();
   await page.waitForFunction(dark=>document.documentElement.classList.contains('dark')===dark,theme==='Dark Mode');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:directory+`/${width}-${theme==='Dark Mode'?'dark':'light'}.png`,fullPage:true});
  }}return {viewports:[1365,390],themes:['light','dark'],horizontal_overflow:false};
 });
 await check('Sign-in preserves new assessment return path',async()=>{
  await page.goto(origin+'/research-verification/new-assessment',{waitUntil:'networkidle'});const url=new URL(page.url());assert.equal(url.pathname,'/login');assert.equal(url.searchParams.get('next'),'/research-verification/new-assessment');return {next:url.searchParams.get('next')};
 });
 await check('Missing assessment does not fabricate results',async()=>{
  await page.goto(origin+'/research-verification/experiment-queue?assessment=00000000-0000-4000-8000-000000000000',{waitUntil:'networkidle'});const text=await page.locator('main').innerText();assert.match(text,/unavailable|not found|could not|unknown/i);assert.ok(!/\b0 reproduced\b/.test(text));return {missing:'Explicit unavailable state'};
 });
 await check('Browser runtime errors',async()=>{assert.deepEqual(pageErrors,[]);return {page_errors:0};});
}catch(e){report.errors.push(e.message);}finally{if(browser)await browser.close();report.passed=!report.errors.length;report.ended_at=new Date().toISOString();await writeFile(directory+'/report.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({directory,...report},null,2));if(!report.passed)process.exitCode=1;}
