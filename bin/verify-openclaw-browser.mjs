// Fixed public production checks. No authenticated writes, model or experiment calls.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {existsSync} from 'node:fs';
import {mkdir,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'../jumpserve-front-end/package.json'));const {chromium}=require('playwright');
if(process.argv.length!==2)throw Error('Fixed public release campaign only.');
const origin='https://jumpserve.quaint-lab.org',base='/research-verification';
const directory=path.join(root,'.test-artifacts/openclaw-browser',new Date().toISOString().replaceAll(':','-'));await mkdir(directory,{recursive:true});
const report={protocol:'openclaw-production-v1',scope:'Public deployed browser regression; authenticated submission is a separately recorded connected-browser campaign.',checks:[],browser_errors:[],model_calls:0,experiment_calls:0,measured_charges_usd:null,reviewer:{identity:'Primary Codex AI implementer',type:'AI',independent:false}};
let browser,page;
async function check(name,run){const tick=Date.now();try{const evidence=await run();report.checks.push({name,passed:true,evidence,wall_seconds:(Date.now()-tick)/1000});console.log('PASS '+name);}catch(e){report.checks.push({name,passed:false,reason:e.message});throw e;}}
try{
 const chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';browser=await chromium.launch({headless:true,executablePath:existsSync(chrome)?chrome:undefined});page=await browser.newPage({viewport:{width:1365,height:900}});page.setDefaultTimeout(25000);page.on('pageerror',e=>report.browser_errors.push(e.message));
 await check('deployed API exposes ready subscription worker and uncapped application defaults',async()=>{const cap=await(await fetch('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities')).json();assert.equal(cap.autonomy.version,'research-autonomy-v3');assert.equal(cap.autonomy.enabled,true);assert.equal(cap.autonomy.defaults.attempts_per_claim,null);assert.equal(cap.autonomy.defaults.maximum_spend_usd,100);assert.equal(cap.autonomy.defaults.elapsed_days,7);assert.equal(cap.autonomy.runtime.runtime,'openclaw-production-v1');assert.equal(cap.autonomy.runtime.status,'ready');return cap.autonomy;});
 let studyPath;
 await check('public previous assessments retain results coverage and complete exports',async()=>{
  await page.goto(origin+base+'/test-results');await page.getByRole('heading',{name:'Published research assessments',exact:true}).waitFor();
  const links=page.locator('h2 a[href^="'+base+'/studies/"]');assert.ok(await links.count()>0);const ipv6=links.filter({hasText:/IPv6/i});studyPath=await(ipv6.count().then(n=>n?ipv6.first():links.first())).then(l=>l.getAttribute('href'));
  await page.goto(origin+studyPath);await page.getByRole('region',{name:'Current claim coverage'}).waitFor();await page.getByRole('heading',{name:'Coverage and uncertainty',exact:true}).waitFor();
  const exportPath=await page.getByRole('link',{name:'Download complete published JSON',exact:true}).getAttribute('href');const response=await fetch(origin+exportPath);assert.equal(response.status,200);const raw=Buffer.from(await response.arrayBuffer());const data=JSON.parse(raw);assert.ok(data.records.claims.length>0);await writeFile(directory+'/published.json',raw);
  const csv=await fetch(origin+exportPath+'?format=csv');assert.equal(csv.status,200);const bytes=Buffer.from(await csv.arrayBuffer());assert.match(bytes.toString(),/units/);await writeFile(directory+'/measurements.csv',bytes);
  return {study_path:studyPath,claims:data.records.claims.length,measurements:data.records.measurements.length,json_sha256:createHash('sha256').update(raw).digest('hex'),csv_sha256:createHash('sha256').update(bytes).digest('hex')};
 });
 await check('recorded IPv6 plots retain units scope and finite geometry in desktop/mobile themes',async()=>{
  await page.goto(origin+'/ipv6-dns-study/test-results');await page.locator('svg[role="img"]:visible').first().waitFor();const states=[];
  for(const width of [1365,390])for(const theme of ['Light Mode','Dark Mode']){
   await page.setViewportSize({width,height:900});await page.getByRole('button',{name:theme,exact:true}).click();await page.waitForFunction(dark=>document.documentElement.classList.contains('dark')===dark,theme==='Dark Mode');
   const plots=page.locator('svg[role="img"]:visible');assert.ok(await plots.count()>0);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const geometry=await plots.evaluateAll(items=>items.flatMap(svg=>[...svg.querySelectorAll('*')].flatMap(n=>['x','y','cx','cy','width','height','d'].map(a=>n.getAttribute(a)).filter(Boolean))));assert.ok(!geometry.some(v=>/NaN|Infinity/.test(v)));
   assert.match(await plots.first().locator('title').first().textContent(),/descriptive|confidence/i);await page.screenshot({path:directory+'/recorded-'+width+'-'+theme.replaceAll(' ','-')+'.png',fullPage:true});states.push({width,theme,plots:await plots.count(),horizontal_overflow:false});
  }
  return {states,data_origin:'Previously archived study measurements; no new scientific experiment'};
 });
 await check('study methods literature gaps and missing-result states remain available',async()=>{
  for(const view of ['methods','literature','gaps']){await page.goto(origin+studyPath+'?view='+view);await page.getByRole('navigation',{name:'Study evidence',exact:true}).waitFor();assert.ok(await page.getByRole('main').innerText());}
  const missing='9fe82c67-2a99-49b9-8bfc-670b69ab1944';await page.goto(origin+base+'/studies/'+missing);await page.getByRole('status').filter({hasText:/no public assessment/i}).waitFor();assert.equal(await page.getByRole('region',{name:'Current claim coverage'}).count(),0);assert.equal((await fetch(origin+base+'/api/studies/'+missing+'/export')).status,404);return {views:['methods','literature','gaps'],missing_coverage:'unknown, not zero',missing_export_status:404};
 });
 await check('anonymous intake and queue preserve sign-in return paths',async()=>{
  for(const target of [base+'/new-study',base+'/experiment-queue?study=9fe82c67-2a99-49b9-8bfc-670b69ab1944']){await page.goto(origin+target);await page.waitForURL(/\/login\?/);assert.equal(new URL(page.url()).searchParams.get('next'),target);}return {legitimate_session_used:false,return_paths_preserved:true};
 });
 assert.deepEqual(report.browser_errors,[]);report.passed=true;
}catch(e){report.passed=false;report.reason=e.stack;process.exitCode=1;if(page)await page.screenshot({path:directory+'/failure.png',fullPage:true});}
finally{if(browser)await browser.close();report.ended_at=new Date().toISOString();await writeFile(directory+'/report.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({directory,passed:report.passed,reason:report.reason}));}
