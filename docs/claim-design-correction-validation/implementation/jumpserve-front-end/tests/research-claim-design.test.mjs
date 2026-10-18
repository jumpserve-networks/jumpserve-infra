import assert from 'node:assert/strict';
import test from 'node:test';
import {registerHooks} from 'node:module';
const hook=registerHooks({resolve(specifier,context,nextResolve){const file=specifier.startsWith('@/lib/')?new URL('../lib/'+specifier.slice(6)+'.ts',import.meta.url).href:specifier.startsWith('./research-')||specifier==='./test-modules'?new URL('../lib/'+specifier.slice(2)+'.ts',import.meta.url).href:specifier;return nextResolve(file,context);}});
const {claimDesignPath,validateClaimDesign,consumeClaimDesignIntent,CLAIM_DESIGN_VERSION}=await import('../lib/research-claim-design.ts');
hook.deregister();
const id='11111111-1111-4111-8111-111111111111';
function fixture(){const document={hypothesis:'The exact recorded claim',protocol:null};return {version:'research-ideas-v1',design_version:CLAIM_DESIGN_VERSION,packets:[{id:'packet',study_id:id,version:1,document,raw_document:JSON.stringify(document),sha256:'a'.repeat(64)}],runs:[],decisions:[],campaigns:[],ready:false,missing:['design'],current_packet_id:'packet',claim_design:{study_id:id,sha256:'b'.repeat(64),raw_document:JSON.stringify({claim:{description:document.hypothesis}}),document:{claim:{description:document.hypothesis}}}};}
test('paper design identity stays in the paper module and rejects invalid routes',()=>{assert.equal(claimDesignPath(id),'/research-verification/experiment-design/'+id);assert.throws(()=>claimDesignPath('../other'));});
test('a paper proposal retains the exact claim and cannot silently weaken it',()=>{assert.equal(validateClaimDesign(fixture(),id).ready,false);for(const change of [s=>s.claim_design.study_id='other',s=>s.claim_design.sha256=null,s=>s.claim_design.document.claim.description='Changed claim',s=>s.design_version='unknown']){const state=fixture();change(state);assert.throws(()=>validateClaimDesign(state,id));}});
test('a design URL cannot invoke AI without a recent consumed click intent',()=>{
 const map=new Map([[`claim-design-start-v1:${id}`,'1000']]);const storage={getItem:k=>map.get(k)??null,removeItem:k=>map.delete(k)};
 assert.equal(consumeClaimDesignIntent(id,storage,1001),true);assert.equal(consumeClaimDesignIntent(id,storage,1001),false);
 for(const time of ['2000','bad','0']){map.set(`claim-design-start-v1:${id}`,time);assert.equal(consumeClaimDesignIntent(id,storage,1000000),false);}
 assert.equal(consumeClaimDesignIntent(id,{getItem(){throw new Error('Storage disabled');},removeItem(){}}),false);
});
