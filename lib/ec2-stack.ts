import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export class Ec2Stack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const allowedSshCidr = this.node.tryGetContext('allowedSshCidr') || '0.0.0.0/0';

    // Use the default VPC
    const vpc = ec2.Vpc.fromLookup(this, 'DefaultVpc', { isDefault: true });

    // Security group: SSH from allowed CIDR
    const securityGroup = new ec2.SecurityGroup(this, 'JumpServeBackendSG', {
      vpc,
      description: 'Security group for JumpServe backend EC2 instance',
      allowAllOutbound: true,
    });
    securityGroup.addIngressRule(
      ec2.Peer.ipv4(allowedSshCidr),
      ec2.Port.tcp(22),
      'SSH access'
    );

    // Import existing SSH public key
    const keyPair = new ec2.CfnKeyPair(this, 'JumpServeKeyPair', {
      keyName: 'jumpserve-key',
      publicKeyMaterial: 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDpUFX4FCzhRW/qeeTPOObCWcqSyVHegWvcAy75lEuPqthfnDsWlUcgVKe3hpxCUxs1rEsAPy8OXgEb52gvEkWQHfUI3cfpdjcCWj9sFd4645dVv+jc6KgnydN6sbOK/9U+AfG+Q47TJNJeffK4UGpUk1xoYBueGfkSqQ/RCJeeNywYoLjQHjhaW1XAeqfYXz62u6NNp/bu8pa4T7mm8kM9KTUNEUU9+cY2OKwVrRBE6QIEjMQ2PxBt89t/j5TuqigiVUa2cvM0/mEDIfIsS88LXCjSbP4Q7CACIrny02cPkYX07JV00l7o8meralwGuv9Gvstsw230V+0q952FWNm6VtLN6EMG50jh8kMt9KYEJUZwDT/mkKlKA4RWL2reE7RNRxOtc4Gla2MEM8/fYnJFKAGi9Bd4f6LS5T8V5MsAVCFK9Mzm/lkTfuFzSPdZIDe8eFNeiBMVZ1/C8HRIiKxXFL+o2TBfkW6gFSkeuf29yPT0NRQrOz6pDwL92FLN/K8=',
    });

    // IAM role with SSM access (for SSM-based deployments and fallback SSH)
    const role = new iam.Role(this, 'JumpServeEc2Role', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    // Ubuntu 22.04 LTS AMI
    const ubuntuAmi = ec2.MachineImage.fromSsmParameter(
      '/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id'
    );

    // User data: install dependencies and clone repo
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      'set -euxo pipefail',
      'apt-get update && apt-get upgrade -y',
      'apt-get install -y iproute2 ethtool python3 python3-pip git net-tools',
      // Clone the backend repo
      'cd /home/ubuntu',
      'git clone https://github.com/jumpserve-networks/jumpserve-back-end.git',
      'chown -R ubuntu:ubuntu jumpserve-back-end',
      // Enable ip forwarding for network namespace benchmarks
      'sysctl -w net.ipv4.ip_forward=1',
      "echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.d/99-jumpserve.conf",
    );

    // EC2 instance
    const instance = new ec2.Instance(this, 'JumpServeBackend', {
      vpc,
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
      machineImage: ubuntuAmi,
      securityGroup,
      keyPair: ec2.KeyPair.fromKeyPairName(this, 'ImportedKeyPair', 'jumpserve-key'),
      role,
      userData,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      associatePublicIpAddress: true,
    });

    // Ensure key pair is created before the instance
    instance.node.addDependency(keyPair);

    // Elastic IP for stable address
    const eip = new ec2.CfnEIP(this, 'JumpServeEIP', {
      domain: 'vpc',
    });

    new ec2.CfnEIPAssociation(this, 'JumpServeEIPAssoc', {
      allocationId: eip.attrAllocationId,
      instanceId: instance.instanceId,
    });

    new cdk.CfnOutput(this, 'InstanceId', {
      value: instance.instanceId,
      description: 'EC2 Instance ID',
    });

    new cdk.CfnOutput(this, 'ElasticIp', {
      value: eip.attrPublicIp,
      description: 'EC2 Elastic IP address',
    });
  }
}
