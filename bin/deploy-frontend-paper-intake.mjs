// Fixed production setup. Keys travel only over stdin to Secrets Manager.
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
if(process.argv.length!==2)throw new Error('This fixed deployment accepts no arguments.');
const temporary=JSON.parse(execFileSync('aws',['configure','export-credentials','--profile','jumpserve','--format','process'],{encoding:'utf8',stdio:['ignore','pipe','pipe']}));
const operations={'sts:get-caller-identity':'GetCallerIdentity','secretsmanager:put-secret-value':'PutSecretValue','amplify:get-app':'GetApp','amplify:get-branch':'GetBranch','amplify:update-app':'UpdateApp','amplify:update-branch':'UpdateBranch'};
const sdk="import json,sys,boto3; p=json.load(sys.stdin); c=p.pop('credentials'); s=boto3.Session(aws_access_key_id=c['AccessKeyId'],aws_secret_access_key=c['SecretAccessKey'],aws_session_token=c['SessionToken']); r=s.client(p['service'],region_name='us-east-1')._make_api_call(p['operation'],p['input']); print(json.dumps(r,default=str))";
function aws(service,operation,input){const method=operations[service+':'+operation];if(!method)throw new Error('Unsupported production setup operation.');return JSON.parse(execFileSync('python3',['-c',sdk],{input:JSON.stringify({credentials:temporary,service,operation:method,input}),encoding:'utf8',stdio:['pipe','pipe','pipe']}));}
const identity=aws('sts','get-caller-identity',{});if(identity.Account!=='395567831870')throw new Error('Expected JumpServe AWS account.');
const local=readFileSync(resolve(root,'../jumpserve-front-end/.env.local'),'utf8');
function setting(name){const value=local.match(new RegExp('^'+name+'=(.+)$','m'))?.[1]?.trim();return value?.startsWith('"')?JSON.parse(value):value;}
if(setting('NEXT_PUBLIC_SUPABASE_URL')!=='https://regphejnlvfpyokpniny.supabase.co')throw new Error('Expected JumpServe database.');
const payload={OPENAI_API_KEY:setting('OPENAI_API_KEY'),SUPABASE_SECRET_KEY:setting('SUPABASE_SECRET_KEY')};
if(!payload.OPENAI_API_KEY?.startsWith('sk-')||!payload.SUPABASE_SECRET_KEY?.startsWith('sb_secret_'))throw new Error('Both local server credentials must be configured.');
const outputDir=resolve(root,'.test-artifacts/frontend-paper-intake-release');mkdirSync(outputDir,{recursive:true});

const env={...process.env,AWS_ACCESS_KEY_ID:temporary.AccessKeyId,AWS_SECRET_ACCESS_KEY:temporary.SecretAccessKey,AWS_SESSION_TOKEN:temporary.SessionToken,AWS_DEFAULT_REGION:'us-east-1',AWS_REGION:'us-east-1'};delete env.AWS_PROFILE;
execFileSync(process.execPath,[resolve(root,'node_modules/aws-cdk/bin/cdk'),'--app','npx ts-node --prefer-ts-exts bin/frontend-paper-intake.ts','deploy','JumpServeFrontendPaperIntakeStack','--require-approval','never','--outputs-file',resolve(outputDir,'outputs.json')],{cwd:root,env,stdio:'inherit'});
const outputs=JSON.parse(readFileSync(resolve(outputDir,'outputs.json'),'utf8')).JumpServeFrontendPaperIntakeStack;
if(!outputs?.SecretArn?.startsWith('arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/frontend/paper-intake-')||outputs.ComputeRoleArn!=='arn:aws:iam::395567831870:role/JumpServeFrontendPaperIntake')throw new Error('Unexpected runtime resource identities.');
aws('secretsmanager','put-secret-value',{SecretId:outputs.SecretArn,SecretString:JSON.stringify(payload)});
const appId='d24jvguj7brnkj',branchName='main';
const app=aws('amplify','get-app',{appId}).app,branch=aws('amplify','get-branch',{appId,branchName}).branch;
if(app.repository!=='https://github.com/jumpserve-networks/jumpserve-front-end')throw new Error('Unexpected Amplify repository.');
// Save only public config and role/reference metadata for rollback.
if(Object.keys(branch.environmentVariables??{}).some(k=>/OPENAI|SUPABASE_SECRET|SERVICE_ROLE/.test(k)))throw new Error('Private keys must not live in Amplify build variables.');
writeFileSync(resolve(outputDir,'previous-amplify-config.json'),JSON.stringify({buildSpec:app.buildSpec,computeRoleArn:branch.computeRoleArn??null,environmentVariables:branch.environmentVariables},null,2)+'\n');
const spec=JSON.parse(app.buildSpec),hook='if [ -f scripts/configure-paper-intake-runtime.mjs ]; then node scripts/configure-paper-intake-runtime.mjs; fi';
const commands=spec.frontend.phases.build.commands;if(!commands.includes(hook))commands.unshift(hook);
aws('amplify','update-app',{appId,buildSpec:JSON.stringify(spec)});
aws('amplify','update-branch',{appId,branchName,computeRoleArn:outputs.ComputeRoleArn,environmentVariables:{...branch.environmentVariables,PAPER_INTAKE_SECRET_ID:outputs.SecretArn}});
const saved=aws('amplify','get-branch',{appId,branchName}).branch;
if(saved.computeRoleArn!==outputs.ComputeRoleArn||saved.environmentVariables.PAPER_INTAKE_SECRET_ID!==outputs.SecretArn)throw new Error('Amplify runtime configuration was not retained.');
console.log(JSON.stringify({configured:true,appId,branch:branchName,secret_arn:outputs.SecretArn,compute_role:outputs.ComputeRoleArn,secret_values_logged:false}));
