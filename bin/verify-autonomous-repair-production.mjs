// Fixed-target, read-only deployed checks in an isolated headless browser.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const require=createRequire(new URL('../../jumpserve-front-end/package.json',import.meta.url));
const {chromium}=require('playwright');
const origin='https://jumpserve.quaint-lab.org',api='https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research',assessment='4055396e-35c0-4962-ba39-cf23e443ad8d';
const directory='.test-artifacts/autonomous-repair-production-browser/'+new Date().toISOString().replaceAll(':','-');await mkdir(directory,{recursive:true});
const report={version:'autonomous-repair-production-browser-v1',started_at:new Date().toISOString(),origin,assessment,checks:[],errors:[],conditional_gaps:['Authenticated upload, confirmation and chat were not exercised in this isolated signed-out browser.','No new paper measurement or claim outcome is inferred from these release checks.'],reviewer:{identity:'Implementing Codex AI',type:'AI',independent:false,human:false},new_model_calls:0,new_experiments:0,measured_charges_usd:null};
let browser;
async function check(name,fn){try{report.checks.push({name,passed:true,evidence:await fn()});console.log('PASS '+name);}catch(error){report.checks.push({name,passed:false,reason:error.message});report.errors.push(error.message);}}
async function read(path,name){const response=await fetch(api+path);const raw=Buffer.from(await response.arrayBuffer());await writeFile(directory+'/'+name,raw);assert.equal(response.status,200);assert.ok(raw.length<2000000);return {data:JSON.parse(raw),sha256:createHash('sha256').update(raw).digest('hex')};}
try{
 browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1365,height:900},timezoneId:'America/Chicago'});const page=await context.newPage();page.setDefaultTimeout(20000);const pageErrors=[];page.on('pageerror',error=>pageErrors.push(error.message));
 let queue;
 await check('actual public queue preserves assessment identities and coverage',async()=>{
  const response=await read(`/studies/${assessment}/queue?public=1&diagnostics=1`,'queue-original.json');queue=response.data;assert.equal(queue.study.id,assessment);assert.equal(queue.coverage.jobs,queue.jobs.length);assert.equal(queue.autonomy.coverage.tasks,queue.autonomy.tasks.length);
  assert.equal(queue.autonomy.defaults.attempts_per_claim,null);assert.equal(queue.autonomy.defaults.maximum_spend_usd,100);
  const claims=queue.autonomy.tasks.filter(t=>t.claim_id);assert.equal(claims.length,5);const counts={};for(const task of claims){counts[task.label]=(counts[task.label]??0)+1;if(task.repair_progress)assert.equal(task.repair_progress.version,'autonomous-repair-v1');}
  await page.goto(origin+'/research-verification/experiment-queue?assessment='+assessment,{waitUntil:'networkidle'});await page.getByText(queue.study.title,{exact:true}).first().waitFor();assert.doesNotMatch(await page.locator('main').innerText(),/Failed to fetch|Assessment status unavailable|Current status is unknown/);
  return {queue_sha256:response.sha256,claims:claims.length,scientific_labels:counts,jobs:queue.jobs.length,repair_states:claims.filter(t=>t.repair_progress).map(t=>t.repair_progress.state),scope:'Recorded snapshot; work may advance after retrieval.'};
 });
 await check('repair incidents and immutable event projections are available through the public backend',async()=>{
  const checked=[];for(const kind of ['autonomy_repairs','autonomy_repair_events']){const value=await read(`/studies/${assessment}/queue?public=1&records=${kind}`,kind+'.json');assert.equal(value.data.kind,kind);assert.equal(value.data.access,'public-read-only');assert.equal(value.data.coverage.returned,value.data.records.length);assert.ok(value.data.records.length<=100);checked.push({kind,returned:value.data.records.length,next_after:value.data.next_after,sha256:value.sha256});}
  await page.getByRole('button',{name:'View assessment records',exact:true}).click();const records=page.getByRole('region',{name:'Shared assessment records',exact:true});
  for(const label of ['Repair incidents and validation','Repair event history']){await records.getByRole('combobox',{name:'Recorded information',exact:true}).click();await page.getByRole('option',{name:label,exact:true}).click();await records.getByText(/records on this page\./).waitFor();assert.equal(await records.getByRole('alert').count(),0);}
  return checked;
 });
 await check('desktop/mobile queue, themes and shared records remain usable',async()=>{
  for(const width of [1365,390])for(const theme of ['Light Mode','Dark Mode']){await page.setViewportSize({width,height:900});await page.getByRole('button',{name:theme,exact:true}).click();await page.waitForFunction(dark=>document.documentElement.classList.contains('dark')===dark,theme==='Dark Mode');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:directory+`/queue-${width}-${theme==='Dark Mode'?'dark':'light'}.png`,fullPage:true});}
  return {widths:[1365,390],themes:['light','dark'],overflow:false};
 });
 await check('previous assessments, explicit missing data and sign-in return paths',async()=>{
  await page.goto(origin+'/research-verification/previous-assessments',{waitUntil:'networkidle'});await page.getByRole('heading',{name:'Previous Assessments',exact:true}).waitFor();
  await page.goto(origin+'/research-verification/experiment-queue?assessment=00000000-0000-4000-8000-000000000000',{waitUntil:'networkidle'});assert.match(await page.locator('main').innerText(),/unavailable|not found|unknown|could not/i);assert.doesNotMatch(await page.locator('main').innerText(),/\b0 reproduced\b/);
  for(const path of ['/research-verification/new-assessment','/research-verification/experiment-queue']){await page.goto(origin+path,{waitUntil:'networkidle'});const url=new URL(page.url());assert.equal(url.pathname,'/login');assert.equal(url.searchParams.get('next'),path);}
  return {missing_state:'explicit',authentication:'anonymous owner access denied; return paths preserved'};
 });
 await check('browser runtime errors',async()=>{assert.deepEqual(pageErrors,[]);return {errors:0};});
}catch(error){report.errors.push(error.message);}finally{if(browser)await browser.close();report.passed=report.errors.length===0;report.ended_at=new Date().toISOString();await writeFile(directory+'/report.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({directory,passed:report.passed,checks:report.checks,errors:report.errors}));if(!report.passed)process.exitCode=1;}
