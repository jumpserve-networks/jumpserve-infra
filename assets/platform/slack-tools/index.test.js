import assert from 'node:assert/strict';
import {test} from 'node:test';
import plugin, {principal} from './index.js';

const context = () => ({messageChannel:'slack', requesterSenderId:'USECOND', nativeChannelId:'C0CEXNJE0HX',
  sessionId:'94fe1491-0e02-492b-b907-4db9ef12d09d', assertInvocationCurrent(){}});

test('all shared-channel humans have tools; other DMs, teams and channels do not', () => {
  assert.equal(principal(context()).sender_id, 'USECOND');
  assert.equal(principal({...context(), requesterSenderId:'team:T01J887B6CE:user:USECOND'}).sender_id,'USECOND');
  for (const change of [{messageChannel:'other'}, {requesterSenderId:'team:TOTHER:user:USECOND'},
    {nativeChannelId:'COTHER'}, {nativeChannelId:'DOTHER'}, {assertInvocationCurrent:undefined}]) {
    assert.equal(principal({...context(), ...change}), null);
  }
  assert.equal(principal({...context(), nativeChannelId:'DPRIVATE', requesterSenderId:'U06EL9LK476'}).sender_id,'U06EL9LK476');
});

test('tool transport takes actor from host and stops when invocation expires', async () => {
  let factory;
  plugin.register({registerTool(value){factory=value;}});
  assert.equal(factory.contextVersion, 2);
  let active=true, request;
  const tools=factory.create({...context(), assertInvocationCurrent(){if(!active) throw new Error('Expired');}});
  const previousFetch=globalThis.fetch;
  process.env.JUMPSERVE_SLACK_BRIDGE='http://127.0.0.1:18801';
  process.env.JUMPSERVE_SLACK_BRIDGE_TOKEN='synthetic-local-token';
  globalThis.fetch=async (url,options)=>{request=JSON.parse(options.body);return {ok:true,json:async()=>({recorded:true})};};
  try {
    await tools[1].execute('fixed-call',{title:'Test',objective:'Synthetic fixture',repositories:['jumpserve-networks/jumpserve-infra']});
    assert.equal(request.actor.sender_id,'USECOND');
    const originalId=request.request_id;
    await tools[1].execute('fixed-call',{});
    assert.equal(request.request_id,originalId);
    active=false; request=null;
    await assert.rejects(tools[0].execute('later',{}),/Expired/);
    assert.equal(request,null);
  } finally {globalThis.fetch=previousFetch;delete process.env.JUMPSERVE_SLACK_BRIDGE;delete process.env.JUMPSERVE_SLACK_BRIDGE_TOKEN;}
});

test('operator tools expose direct controls to shared-channel members with stable call identities', async () => {
  let factory, registered;
  plugin.register({registerTool(value, options){factory=value;registered=options.names;}});
  const tools=factory.create(context());
  assert.deepEqual(tools.map(t=>t.name),registered);
  const control=tools.find(t=>t.name==='jumpserve_control');
  const inspect=tools.find(t=>t.name==='jumpserve_task');
  assert.deepEqual(control.parameters.required,['action']);
  const previousFetch=globalThis.fetch;
  process.env.JUMPSERVE_SLACK_BRIDGE='http://127.0.0.1:18801';
  process.env.JUMPSERVE_SLACK_BRIDGE_TOKEN='synthetic-local-token';
  const requests=[];
  globalThis.fetch=async (_url, options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>({recorded:true})};};
  try {
    await control.execute('pause-call',{action:'pause'});
    await control.execute('pause-call',{action:'pause'});
    assert.equal(requests[0].request_id,requests[1].request_id);
    assert.equal(requests[0].actor.sender_id,'USECOND');
    assert.deepEqual(requests[0].payload,{action:'pause'});
    assert.equal(requests[0].operation,'jumpserve_control');
    const task='d9841346-7f7d-48be-b51d-d6d1b0c813ae';
    await inspect.execute('inspect-call',{task_id:task});
    assert.equal(requests[2].operation,'jumpserve_task');
    assert.notEqual(requests[0].request_id,requests[2].request_id);
  } finally {globalThis.fetch=previousFetch;delete process.env.JUMPSERVE_SLACK_BRIDGE;delete process.env.JUMPSERVE_SLACK_BRIDGE_TOKEN;}
});
