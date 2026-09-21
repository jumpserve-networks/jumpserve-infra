import * as cdk from 'aws-cdk-lib/core';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { addBenchmarkImagePipelineRole } from '../lib/benchmark-image-pipeline';

test('image workflow trusts only backend main and limits temporary role permissions', () => {
  const stack = new cdk.Stack(new cdk.App(), 'PipelineTest', {
    env: { account: '395567831870', region: 'us-east-1' },
  });
  const instanceRole = iam.Role.fromRoleArn(stack, 'InstanceRole', 'arn:aws:iam::395567831870:role/BenchmarkInstance');
  addBenchmarkImagePipelineRole(stack, instanceRole, 'arn:aws:lambda:us-east-1:395567831870:function:Launch');
  const template = Template.fromStack(stack);
  template.hasResourceProperties('AWS::IAM::Role', {
    RoleName: 'JumpServeBenchmarkImageBuilder',
    AssumeRolePolicyDocument: { Statement: [Match.objectLike({
      Action: 'sts:AssumeRoleWithWebIdentity',
      Condition: { StringEquals: {
        'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        'token.actions.githubusercontent.com:sub': 'repo:jumpserve-networks/jumpserve-back-end:ref:refs/heads/main',
      } },
    })], Version: '2012-10-17' },
  });
  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({
      Action: 'ec2:CreateTags',
      Resource: [
        Match.anyValue(),
        { 'Fn::Join': ['', ['arn:', { Ref: 'AWS::Partition' }, ':ec2:us-east-1::image/*']] },
        { 'Fn::Join': ['', ['arn:', { Ref: 'AWS::Partition' }, ':ec2:us-east-1::snapshot/*']] },
      ],
      Condition: { StringEquals: { 'ec2:CreateAction': ['RunInstances', 'CreateImage'] } },
    }), Match.objectLike({
      Action: 'ec2:TerminateInstances',
      Condition: { StringEquals: { 'ec2:ResourceTag/Project': 'JumpServe' } },
    }), Match.objectLike({
      Action: ['iam:AttachRolePolicy', 'iam:DetachRolePolicy'],
      Condition: { ArnEquals: { 'iam:PolicyARN': 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore' } },
    })]), Version: '2012-10-17' },
  });
  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({
      Action: ['lambda:GetFunctionConfiguration', 'lambda:InvokeFunction'],
      Resource: 'arn:aws:lambda:us-east-1:395567831870:function:Launch',
    })]) },
  });

});
