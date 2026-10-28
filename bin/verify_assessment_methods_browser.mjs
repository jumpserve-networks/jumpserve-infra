// Fixed, read-only public rerun checks in an owned headless browser.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire(new URL('../../jumpserve-front-end/package.json',import.meta.url));
const {chromium}=require('playwright');
const id='a3bad34f-a9b5-44bb-be46-e1800cf1cf89';
const origin='https://jumpserve.quaint-lab.org';
const path='/research-verification/experiment-queue?assessment='+id;
const directory='.test-artifacts/assessment-methods-release-v1/browser/'+new Date().toISOString().replaceAll(':','-');
await mkdir(directory,{recursive:true});
const report={protocol:'autonomy-methods-release-v1',assessment_id:id,access:'anonymous read-only',checks:[],reviewer:{identity:'Codex AI implementation author',type:'AI',independent:false},authenticated_submission_verified:false};
let browser;
try{
  browser=await chromium.launch({headless:true,channel:'chrome'});
  for(const width of [1365,390]){
    const context=await browser.newContext({viewport:{width,height:900}});
    try{
      const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
      const pending=page.waitForResponse(r=>r.url().includes('/studies/'+id+'/queue')&&r.request().method()==='GET',{timeout:30000});
      const navigation=await page.goto(origin+path,{waitUntil:'domcontentloaded'});assert.equal(navigation.status(),200);
      const response=await pending;assert.equal(response.status(),200);const data=await response.json();
      assert.equal(data.access,'public-read-only');assert.equal(data.study.id,id);
      assert.equal(data.study.title,'The Impact of Packet Loss on TCP Throughput in Controlled Networks');
      assert.equal(data.autonomy.tasks.filter(t=>t.claim_id).length,9);
      assert.equal(data.autonomy.workflows[0].max_spend_cents,10000);assert.equal(data.autonomy.workflows[0].max_attempts,null);
      await page.getByText(data.study.title,{exact:true}).first().waitFor();
      for(const theme of ['Light Mode','Dark Mode']){
        await page.getByRole('button',{name:theme,exact:true}).click();
        await page.waitForFunction(dark=>document.documentElement.classList.contains('dark')===dark,theme==='Dark Mode');
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        report.alerts??=[];report.alerts.push({width,theme,all:await page.locator('[role=alert]').allTextContents()});
        assert.equal(await page.locator('[data-testid=public-experiment-queue] [role=alert]').count(),0);
        await page.screenshot({path:directory+'/'+width+'-'+theme.split(' ')[0]+'.png',fullPage:true});
      }
      await page.getByRole('button',{name:'View assessment records',exact:true}).click();
      await page.getByRole('button',{name:'Hide assessment records',exact:true}).waitFor();
      assert.deepEqual(errors,[]);report.checks.push({width,themes:['light','dark'],queue_http_status:200,claims:9,shared_records_expand:true});
    }finally{await context.close();}
  }
  report.passed=true;
}catch(error){report.passed=false;report.failure=error.message;}
finally{
  if(browser)await browser.close();report.ended_at=new Date().toISOString();
  await writeFile(directory+'/report.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({directory,passed:report.passed,failure:report.failure}));
  process.exitCode=report.passed?0:1;
}
