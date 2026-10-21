import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as assets from 'aws-cdk-lib/aws-s3-assets';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import {Construct} from 'constructs';
import * as path from 'path';
import * as fs from 'fs';
import {createHash} from 'crypto';

/** Private lab inference host. No public listener or experiment-launch rights. */
export class OpenClawWorker extends Construct {
  readonly instance: ec2.Instance;
  constructor(scope: Construct,id: string,props: {vpc:ec2.IVpc;runtime:string;secret:secretsmanager.ISecret}) {
    super(scope,id);
    if(cdk.Stack.of(this).account!=='395567831870')throw new Error('OpenClaw worker requires the verified JumpServe account.');
    const directory=path.join(__dirname,'..','.runtime-openclaw');
    const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'..','research-workflow-runtime.json'),'utf8'));
    for(const [name,sha] of Object.entries(manifest.files))if(createHash('sha256').update(fs.readFileSync(path.join(props.runtime,name))).digest('hex')!==sha)throw new Error('OpenClaw controller bytes differ from the declared runtime.');
    const lock=JSON.parse(fs.readFileSync(path.join(__dirname,'..','openclaw-worker-runtime.json'),'utf8'));
    for(const [name,sha] of Object.entries(lock.files)) {
      if(name.includes('..')||path.isAbsolute(name)||createHash('sha256').update(fs.readFileSync(path.join(directory,name))).digest('hex')!==sha)throw new Error('Pinned OpenClaw worker inputs differ. Run prepare-openclaw-worker.py.');
    }
    const dependencies=new assets.Asset(this,'Dependencies',{path:directory});
    const runtime=new assets.Asset(this,'Runtime',{path:props.runtime});
    const role=new iam.Role(this,'Role',{assumedBy:new iam.ServicePrincipal('ec2.amazonaws.com'),managedPolicies:[iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')]});
    props.secret.grantRead(role);
    role.addToPolicy(new iam.PolicyStatement({actions:['s3:GetObject'],resources:[dependencies.bucket.arnForObjects(dependencies.s3ObjectKey),runtime.bucket.arnForObjects(runtime.s3ObjectKey)]}));
    const sg=new ec2.SecurityGroup(this,'Network',{vpc:props.vpc,description:'OpenClaw private worker; SSM only, no ingress',allowAllOutbound:false});
    sg.addEgressRule(ec2.Peer.anyIpv4(),ec2.Port.tcp(443),'Pinned software, OAuth, provider and private persistence over HTTPS');
    sg.addEgressRule(ec2.Peer.anyIpv4(),ec2.Port.tcp(80),'Signed Amazon Linux package repositories');
    const userData=ec2.UserData.forLinux();
    userData.addCommands(
      'set -eu','umask 077',
      'dnf install -y python3.12 python3.12-pip unzip tar xz awscli-2',
      'test "$(aws sts get-caller-identity --query Account --output text)" = "395567831870"',
      'useradd --system --create-home --home-dir /var/lib/jumpserve-openclaw jumpserve || true',
      'mkdir -p /opt/jumpserve/runtime /opt/jumpserve/dependencies /var/lib/jumpserve-openclaw/auth /var/lib/jumpserve-openclaw/spool',
      `aws s3 cp s3://${dependencies.s3BucketName}/${dependencies.s3ObjectKey} /opt/jumpserve/dependencies.zip --region us-east-1`,
      `aws s3 cp s3://${runtime.s3BucketName}/${runtime.s3ObjectKey} /opt/jumpserve/runtime.zip --region us-east-1`,
      'unzip -q /opt/jumpserve/dependencies.zip -d /opt/jumpserve/dependencies',
      'unzip -q /opt/jumpserve/runtime.zip -d /opt/jumpserve/runtime',
      'bash /opt/jumpserve/dependencies/install.sh',
      `printf '%s\n' 'SUPABASE_URL=https://regphejnlvfpyokpniny.supabase.co' 'SUPABASE_SECRET_ARN=${props.secret.secretArn}' 'AWS_DEFAULT_REGION=us-east-1' 'RESEARCH_AI_RUNTIME=openclaw-production-v1' > /etc/jumpserve-openclaw.env`,
      'chmod 600 /etc/jumpserve-openclaw.env',
      'chown -R jumpserve:jumpserve /var/lib/jumpserve-openclaw',
      'install -m 644 /opt/jumpserve/dependencies/jumpserve-openclaw.service /etc/systemd/system/jumpserve-openclaw.service',
      'systemctl daemon-reload','systemctl enable --now jumpserve-openclaw.service'
    );
    this.instance=new ec2.Instance(this,'Host',{vpc:props.vpc,vpcSubnets:{subnetType:ec2.SubnetType.PUBLIC},instanceType:new ec2.InstanceType('t3.medium'),machineImage:ec2.MachineImage.latestAmazonLinux2023(),role,securityGroup:sg,requireImdsv2:true,associatePublicIpAddress:true,userData,userDataCausesReplacement:false,blockDevices:[{deviceName:'/dev/xvda',volume:ec2.BlockDeviceVolume.ebs(24,{encrypted:true,deleteOnTermination:false,volumeType:ec2.EbsDeviceVolumeType.GP3})}]});
    cdk.Tags.of(this.instance).add('Purpose','JumpServe OpenClaw subscription inference');
    new cdk.CfnOutput(cdk.Stack.of(this),'OpenClawWorkerInstanceId',{value:this.instance.instanceId,description:'Private SSM-managed lab worker; ChatGPT grant stays on its encrypted host.'});
    new cdk.CfnOutput(cdk.Stack.of(this),'OpenClawRuntimeBucket',{value:runtime.s3BucketName});
    new cdk.CfnOutput(cdk.Stack.of(this),'OpenClawRuntimeObject',{value:runtime.s3ObjectKey});
  }
}
