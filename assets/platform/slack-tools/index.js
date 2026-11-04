import { createHash } from 'node:crypto';

const TEAM = 'T01J887B6CE';
const CHANNEL = 'C0CEXNJE0HX';
const OWNER = 'U06EL9LK476';
const repositories = ['jumpserve-networks/jumpserve-front-end', 'jumpserve-networks/jumpserve-back-end', 'jumpserve-networks/jumpserve-infra'];
const names = ['jumpserve_status', 'jumpserve_request', 'jumpserve_task', 'jumpserve_control'];

export function principal(context) {
  if (context.messageChannel !== 'slack' || typeof context.assertInvocationCurrent !== 'function') return null;
  const raw = context.requesterSenderId || '';
  const match = /^(?:team:T01J887B6CE:user:)?(U[A-Z0-9]+)$/.exec(raw);
  const sender = match?.[1];
  const channel = context.nativeChannelId;
  if (!sender || !(channel === CHANNEL || /^D[A-Z0-9]+$/.test(channel || '') && sender === OWNER)) return null;
  if (!/^[0-9a-f-]{36}$/i.test(context.sessionId || '')) return null;
  return {team_id: TEAM, channel_id: channel, sender_id: sender, session_id: context.sessionId};
}

function identity(session, call) {
  const h = createHash('sha256').update(session + '\0' + call).digest('hex').slice(0, 32).split('');
  h[12] = '5'; h[16] = ['8', '9', 'a', 'b'][parseInt(h[16], 16) % 4];
  const value = h.join('');
  return `${value.slice(0,8)}-${value.slice(8,12)}-${value.slice(12,16)}-${value.slice(16,20)}-${value.slice(20)}`;
}

export default {
  id: 'jumpserve-supervisor',
  name: 'JumpServe supervisor tools',
  register(api) {
    api.registerTool({contextVersion: 2, create(context) {
      const actor = principal(context);
      if (!actor) return null;
      function tool(name, description, properties, required) {
        return {
          name, label: name, description,
          parameters: {type: 'object', properties, required, additionalProperties: false},
          async execute(callId, params, signal) {
            context.assertInvocationCurrent();
            const origin = process.env.JUMPSERVE_SLACK_BRIDGE;
            const token = process.env.JUMPSERVE_SLACK_BRIDGE_TOKEN;
            if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin || '') || !token) throw new Error('Supervisor bridge is unavailable');
            const payload = {actor, request_id: identity(actor.session_id, callId), operation: name, payload: params};
            // Identity comes from the admitted host context, never model fields.
            context.assertInvocationCurrent();
            const response = await fetch(origin + '/tools', {
              method: 'POST', headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
              body: JSON.stringify(payload), signal: signal || AbortSignal.timeout(45000), redirect: 'error',
            });
            if (!response.ok) throw new Error('Supervisor tool did not confirm its operation; do not invent or replay it');
            const result = await response.json();
            context.assertInvocationCurrent();
            return {content: [{type: 'text', text: JSON.stringify(result)}], details: result};
          },
        };
      }
      return [
        tool('jumpserve_status', 'Read current supervisor heartbeat, pause/release settings, aggregate task counts and tasks shared in this conversation. Use this for current status; do not infer health from old chat messages.', {}, []),
        tool('jumpserve_request', 'Queue a concrete improvement explicitly requested by a human in this Slack conversation. Existing supervisor checks, limits and release controls apply. A queued request is not completed work. Do not queue work for casual discussion or duplicate an existing request.', {
          title: {type: 'string', minLength: 1, maxLength: 160},
          objective: {type: 'string', minLength: 1, maxLength: 12000},
          repositories: {type: 'array', minItems: 1, maxItems: 3, uniqueItems: true, items: {type: 'string', enum: repositories}},
        }, ['title', 'objective', 'repositories']),
        tool('jumpserve_task', 'Inspect current progress, blockers, changes, releases and model-call states for a task shared in this conversation.', {
          task_id: {type: 'string', format: 'uuid'},
        }, ['task_id']),
        tool('jumpserve_control', 'Execute an explicitly requested supervisor operator action without another owner permission exchange. Pause/resume work, disable/enable automatic qualified merges/releases, or cancel a shared task. Supply task_id only for cancel. Report the recorded state; in-flight operations still reconcile.', {
          action: {type: 'string', enum: ['pause', 'resume', 'disable-releases', 'enable-releases', 'cancel']},
          task_id: {type: ['string','null'], format: 'uuid', description: 'Required task UUID for cancel. Use null for pause, resume, disable-releases, or enable-releases. Never invent a task UUID for a global action.'},
        }, ['action']),
      ];
    }}, {names});
  },
};
