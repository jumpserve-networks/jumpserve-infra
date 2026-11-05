import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as assets from 'aws-cdk-lib/aws-s3-assets';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import {Construct} from 'constructs';
import * as path from 'path';
import * as fs from 'fs';
import {createHash} from 'crypto';

/** Separate compute; no new OAuth grant or ingress on the existing host. */
export class IntakeWorker extends Construct {
  readonly instance: ec2.Instance;
  constructor(scope: Construct,id: string,props:{vpc:ec2.IVpc;ownerRoleArn:string;secret:secrets.ISecret}) {
    super(scope,id);
    if(cdk.Stack.of(this).account!=='395567831870' || !/^arn:aws:iam::395567831870:role\/JumpServeOpenClawStack-[A-Za-z0-9_-]+$/.test(props.ownerRoleArn))throw new Error('Verified existing refresh owner required.');
    const root=path.join(__dirname,'..');
    const directory=path.join(root,'.runtime-intake');
    const manifest=JSON.parse(fs.readFileSync(path.join(directory,'intake-manifest.json'),'utf8'));
    const declared=JSON.parse(fs.readFileSync(path.join(root,'intake-worker-runtime.json'),'utf8'));
    if(manifest.version!=='warm-intake-v1'||!/^[a-f0-9]{40}$/.test(manifest.source_revision)||JSON.stringify(manifest)!==JSON.stringify(declared))throw new Error('Qualified pinned intake runtime required.');
    for(const [name,sha] of Object.entries(manifest.files)) {
      if(name.includes('..')||path.isAbsolute(name)||createHash('sha256').update(fs.readFileSync(path.join(directory,name))).digest('hex')!==sha)throw new Error('Intake runtime source changed.');
    }
    const lock=JSON.parse(fs.readFileSync(path.join(root,'openclaw-worker-runtime.json'),'utf8'));
    const dependencyDir=path.join(root,'.runtime-openclaw');
    for(const [name,sha] of Object.entries(lock.files))if(createHash('sha256').update(fs.readFileSync(path.join(dependencyDir,name))).digest('hex')!==sha)throw new Error('Pinned native dependencies differ.');
    const runtime=new assets.Asset(this,'Runtime',{path:directory});
    const dependencies=new assets.Asset(this,'Dependencies',{path:dependencyDir});
    const service=new assets.Asset(this,'Service',{path:path.join(root,'assets/openclaw/jumpserve-intake.service')});
    const publisher=new assets.Asset(this,'PublisherService',{path:path.join(root,'assets/openclaw/jumpserve-intake-access.service')});
    const role=new iam.Role(this,'Role',{assumedBy:new iam.ServicePrincipal('ec2.amazonaws.com'),managedPolicies:[iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')]});
    props.secret.grantRead(role);runtime.grantRead(role);dependencies.grantRead(role);service.grantRead(role);
    const parameter='arn:aws:ssm:us-east-1:395567831870:parameter/jumpserve/intake-access-v1';
    role.addToPolicy(new iam.PolicyStatement({actions:['ssm:GetParameter'],resources:[parameter]}));
    role.addToPolicy(new iam.PolicyStatement({effect:iam.Effect.DENY,actions:['ssm:GetParameter','ssm:GetParameters','ssm:GetParametersByPath'],notResources:[parameter]}));
    const owner=iam.Role.fromRoleArn(this,'RefreshOwner',props.ownerRoleArn,{mutable:true});
    owner.addToPrincipalPolicy(new iam.PolicyStatement({actions:['ssm:PutParameter'],resources:[parameter]}));
    runtime.grantRead(owner);publisher.grantRead(owner);
    const sg=new ec2.SecurityGroup(this,'Network',{vpc:props.vpc,allowAllOutbound:false,description:'Dedicated intake: SSM only, no ingress or experiment execution'});
    sg.addEgressRule(ec2.Peer.anyIpv4(),ec2.Port.tcp(443),'Pinned dependencies, private storage and authorized inference');
    sg.addEgressRule(ec2.Peer.anyIpv4(),ec2.Port.tcp(80),'Signed Amazon Linux repositories');
    const userData=ec2.UserData.forLinux();
    userData.addCommands('set -eu','umask 077','dnf install -y python3.12 python3.12-pip unzip tar xz awscli-2',
      'test "$(aws sts get-caller-identity --query Account --output text --region us-east-1)" = 395567831870',
      'useradd --system --create-home --home-dir /var/lib/jumpserve-openclaw jumpserve || true',
      'mkdir -p /opt/jumpserve/dependencies /opt/jumpserve/intake-runtime /var/lib/jumpserve-openclaw/auth /var/lib/jumpserve-intake',
      `aws s3 cp s3://${dependencies.s3BucketName}/${dependencies.s3ObjectKey} /opt/jumpserve/dependencies.zip --region us-east-1`,
      'unzip -q /opt/jumpserve/dependencies.zip -d /opt/jumpserve/dependencies','bash /opt/jumpserve/dependencies/install.sh',
      `aws s3 cp s3://${runtime.s3BucketName}/${runtime.s3ObjectKey} /opt/jumpserve/intake.zip --region us-east-1`,
      'unzip -q /opt/jumpserve/intake.zip -d /opt/jumpserve/intake-runtime',
      `/opt/jumpserve/python/bin/python -c 'import hashlib,json,pathlib; r=pathlib.Path("/opt/jumpserve/intake-runtime"); m=json.loads((r/"intake-manifest.json").read_bytes()); assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==h for n,h in m["files"].items())'`,
      // Restrictive bootstrap umask also affects directories created by unzip.
      // Only immutable code/policies become readable; auth/state stay private.
      'chmod -R a+rX /opt/jumpserve/intake-runtime',
      `runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c 'import sys; sys.path.insert(0,"/opt/jumpserve/intake-runtime"); import intake_worker; intake_worker.runtime.verify_runtime()'`,
      `printf '%s\n' 'SUPABASE_URL=https://regphejnlvfpyokpniny.supabase.co' 'SUPABASE_SECRET_ARN=${props.secret.secretArn}' 'AWS_DEFAULT_REGION=us-east-1' 'RESEARCH_AI_RUNTIME=openclaw-production-v1' 'RESEARCH_CATEGORY_BUDGETS_ENABLED=true' 'INTAKE_HOME=/var/lib/jumpserve-intake' > /etc/jumpserve-intake.env`,
      'chmod 600 /etc/jumpserve-intake.env','chown -R jumpserve:jumpserve /var/lib/jumpserve-intake',
      `aws s3 cp s3://${service.s3BucketName}/${service.s3ObjectKey} /etc/systemd/system/jumpserve-intake.service --region us-east-1`,
      'chmod 644 /etc/systemd/system/jumpserve-intake.service','systemctl daemon-reload','systemctl enable --now jumpserve-intake.service');
    this.instance=new ec2.Instance(this,'Host',{vpc:props.vpc,vpcSubnets:{subnetType:ec2.SubnetType.PUBLIC},instanceType:new ec2.InstanceType('t3.large'),
      machineImage:ec2.MachineImage.genericLinux({'us-east-1':lock.worker_ami_id}),role,securityGroup:sg,requireImdsv2:true,userData,
      blockDevices:[{deviceName:'/dev/xvda',volume:ec2.BlockDeviceVolume.ebs(32,{encrypted:true,deleteOnTermination:false,volumeType:ec2.EbsDeviceVolumeType.GP3})}]});
    // Protected cloud workflows can inspect and maintain this exact host using
    // fresh OIDC sessions, without desktop login or static integration keys.
    const releaseRole=iam.Role.fromRoleName(this,'CloudRelease','JumpServePlatformRelease',{mutable:true});
    const hostArn=cdk.Stack.of(this).formatArn({service:'ec2',resource:'instance',resourceName:this.instance.instanceId});
    releaseRole.addToPrincipalPolicy(new iam.PolicyStatement({actions:['ssm:SendCommand'],resources:[hostArn,'arn:aws:ssm:us-east-1::document/AWS-RunShellScript']}));
    releaseRole.addToPrincipalPolicy(new iam.PolicyStatement({actions:['ec2:GetConsoleOutput'],resources:[hostArn]}));
    releaseRole.addToPrincipalPolicy(new iam.PolicyStatement({actions:['ec2:DescribeInstances','ssm:DescribeInstanceInformation'],resources:['*']}));
    releaseRole.addToPrincipalPolicy(new iam.PolicyStatement({actions:['cloudformation:DescribeStacks'],resources:['arn:aws:cloudformation:us-east-1:395567831870:stack/JumpServeIntakeStack/*']}));
    new cdk.CfnOutput(cdk.Stack.of(this),'IntakeInstanceId',{value:this.instance.instanceId});
    new cdk.CfnOutput(cdk.Stack.of(this),'IntakeRuntimeBucket',{value:runtime.s3BucketName});
    new cdk.CfnOutput(cdk.Stack.of(this),'IntakeRuntimeObject',{value:runtime.s3ObjectKey});
    new cdk.CfnOutput(cdk.Stack.of(this),'IntakePublisherBucket',{value:publisher.s3BucketName});
    new cdk.CfnOutput(cdk.Stack.of(this),'IntakePublisherObject',{value:publisher.s3ObjectKey});
    new cdk.CfnOutput(cdk.Stack.of(this),'IntakeSourceBinding',{value:manifest.source_binding});
  }
}
