// Fixed public production checks in an owned headless browser; no user writes.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire(new URL('../../jumpserve-front-end/package.json',import.meta.url));const {chromium}=require('playwright');
assert.ok(process.argv.length===2||process.argv.length===3&&process.argv[2]==='--amended');
const amended=process.argv[2]==='--amended',id='4055396e-35c0-4962-ba39-cf23e443ad8d',origin='https://jumpserve.quaint-lab.org';
const path='/research-verification/experiment-queue?assessment='+id,directory='.test-artifacts/assessment-recovery-release-v1/browser/'+new Date().toISOString().replaceAll(':','-');await mkdir(directory,{recursive:true});
const report={protocol:'assessment-recovery-release-v1',assessment:id,amended,access:'anonymous read-only',checks:[],actual_authenticated_request:false,reviewer:{identity:'Implementing Codex assistant',type:'AI',independent:false,human:false}};let browser;
try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 for(const width of [1365,390]){
  const context=await browser.newContext({viewport:{width,height:900}});
  try{
   const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   const pending=page.waitForResponse(response=>response.url().includes('/studies/'+id+'/queue')&&response.request().method()==='GET');assert.equal((await page.goto(origin+path,{waitUntil:'domcontentloaded'})).status(),200);
   const response=await pending;assert.equal(response.status(),200);const data=await response.json();assert.equal(data.study.id,id);assert.equal(data.access,'public-read-only');assert.equal(data.autonomy.tasks.filter(t=>t.claim_id).length,5);assert.equal(data.autonomy.workflows[0].max_spend_cents,amended?100000:10000);
   await page.getByText(data.study.title,{exact:true}).first().waitFor();assert.equal(await page.locator('[data-testid=public-experiment-queue] [role=alert]').count(),0);
   await page.getByText(`committed of $${(data.autonomy.workflows[0].max_spend_cents/100).toFixed(2)} · deadline`,{exact:false}).waitFor();
   assert.ok(!(await page.locator('main').innerText()).includes('Shared recorded progress for this assessment.'));
   for(const theme of ['Light Mode','Dark Mode']){
    await page.getByRole('button',{name:theme,exact:true}).click();await page.waitForFunction(dark=>document.documentElement.classList.contains('dark')===dark,theme==='Dark Mode');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:directory+'/'+width+'-'+theme.split(' ')[0]+'.png',fullPage:true});
   }
   await page.getByRole('button',{name:'View assessment records',exact:true}).click();await page.getByRole('region',{name:'Shared assessment records'}).waitFor();
   const first=page.locator('[id^="claim-task-"]').first();await first.getByRole('button',{name:'View prompts and responses',exact:true}).click();await first.locator('article').first().waitFor();
   assert.deepEqual(errors,[]);report.checks.push({width,themes:['light','dark'],claims:5,max_spend_cents:data.autonomy.workflows[0].max_spend_cents,rendered_budget_matches_record:true,shared_records:true,retained_turns:true,overflow:false,removed_footer_absent:true});
   await page.goto(origin+'/research-verification/experiment-queue?assessment=invalid');await page.getByRole('alert').filter({hasText:/invalid assessment/i}).waitFor();report.checks.push({width,invalid_identity_state:true});
  }finally{await context.close();}
 }
 report.passed=true;
}catch(error){report.passed=false;report.failure=error.message;}
finally{if(browser)await browser.close();report.ended_at=new Date().toISOString();await writeFile(directory+'/report.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({directory,passed:report.passed,failure:report.failure}));process.exitCode=report.passed?0:1;}
