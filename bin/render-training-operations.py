"""Render the CloudFormation stack for JumpServe's fixed coordinator operations."""

import json
from pathlib import Path


def sub(value):
    return {"Fn::Sub": value}


def ref(value):
    return {"Ref": value}


def allow(action, resource, condition=None):
    statement = {"Effect": "Allow", "Action": action, "Resource": resource}
    if condition:
        statement["Condition"] = condition
    return statement


def policy(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


def document(name, mode, parameters, timeout):
    source = Path(__file__).with_name("training-operations.py").read_text()
    arguments = " ".join('"${SSM_' + parameter + '}"' for parameter in parameters)
    launcher = (
        'set -eu\nexec /usr/sbin/runuser -u ec2-user -- /usr/bin/env -i '
        'HOME=/home/ec2-user PATH=/usr/local/bin:/usr/bin:/bin AWS_PAGER= '
        'AWS_IGNORE_CONFIGURED_ENDPOINT_URLS=true /usr/bin/python3 -I - "'
    )
    return {
        "Type": "AWS::SSM::Document",
        "Properties": {
            "Name": name, "DocumentType": "Command", "TargetType": "/AWS::EC2::Instance",
            "UpdateMethod": "NewVersion",
            "Content": {
                "schemaVersion": "2.2",
                "description": "Run the fixed JumpServe " + mode + " operation",
                "parameters": {
                    key: {"type": "String", "interpolationType": "ENV_VAR", "allowedPattern": pattern}
                    | ({"default": default} if default is not None else {})
                    for key, (pattern, default) in parameters.items()
                },
                "mainSteps": [{
                    "action": "aws:runShellScript", "name": "trainingOperation",
                    "inputs": {"timeoutSeconds": str(timeout), "runCommand": [
                        {"Fn::Join": ["", [
                            launcher, ref("TrainingBatchBucketName"),
                            f'" {mode} {arguments} <<\'TRAINING_OPERATIONS_PY\'\n'
                            + source + "TRAINING_OPERATIONS_PY\n",
                        ]]},
                    ]},
                }],
            },
        },
    }


def template():
    aws_id = "arn:${AWS::Partition}"
    bucket = aws_id + ":s3:::${TrainingBatchBucketName}"
    coordinator = sub(aws_id + ":ec2:${AWS::Region}:${AWS::AccountId}:instance/${CoordinatorInstance}")
    document_arn = aws_id + ":ssm:${AWS::Region}:${AWS::AccountId}:document/"
    archives = sub(bucket + "/runtime/archives/*")
    receipts = sub(bucket + "/runtime/receipts/*")
    diagnostics = sub(bucket + "/diagnostics/*")
    diagnostic_command = allow("ssm:SendCommand", [sub(document_arn + "${DiagnosticsDocument}"), coordinator])
    release_command = allow("ssm:SendCommand", [sub(document_arn + "${ReleaseDocument}"), coordinator])
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Scoped and renewable JumpServe synthetic-training coordinator operations.",
        "Parameters": {
            "CoordinatorInstance": {"Type": "AWS::EC2::Instance::Id"},
            "TrainingBatchBucketName": {"Type": "String", "AllowedPattern": "^[a-z0-9-]{3,63}$"},
        },
        "Resources": {
            "GithubOidc": {
                "Type": "AWS::IAM::OIDCProvider",
                "Properties": {"Url": "https://token.actions.githubusercontent.com", "ClientIdList": ["sts.amazonaws.com"]},
            },
            "ReleaseDocument": document("JumpServeInstallTrainingRelease", "release", {
                "RequestId": ("^[0-9]{1,20}-[0-9]{1,8}$", None),
                "ArchiveSha": ("^[a-f0-9]{64}$", None),
                "Revision": ("^[a-f0-9]{40}$", None),
            }, 500),
            "DiagnosticsDocument": document("JumpServeTrainingBatchDiagnostics", "diagnostics", {
                "RequestId": ("^[a-f0-9]{32}$", None),
                "BatchId": ("^[1-9][0-9]{0,9}$", None),
                "Mode": ("^(inspect|recover)$", "inspect"),
                "Paper": ("^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$", "all"),
                "Stage": ("^(generator|verifier)$", "generator"),
            }, 1_100),
            "GithubReleaseRole": {
                "Type": "AWS::IAM::Role",
                "Properties": {
                    "RoleName": "JumpServeTrainingRelease",
                    "AssumeRolePolicyDocument": policy({
                        "Effect": "Allow", "Action": "sts:AssumeRoleWithWebIdentity",
                        "Principal": {"Federated": ref("GithubOidc")},
                        "Condition": {"StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                            "token.actions.githubusercontent.com:sub": (
                                "repo:jumpserve-networks/jumpserve-front-end:ref:refs/heads/main"),
                        }},
                    }),
                    "Policies": [{"PolicyName": "TrainingRuntimeRelease", "PolicyDocument": policy(
                        release_command, allow("s3:GetObject", [archives, receipts]),
                        allow("s3:PutObject", archives, {"Null": {"s3:if-none-match": "false"}}),
                    )}],
                },
            },
            "LocalDiagnosticsAccess": {
                "Type": "AWS::IAM::Policy",
                "Properties": {"PolicyName": "JumpServeTrainingDiagnostics", "Roles": ["JumpServeTrainingLocalRead"],
                               "PolicyDocument": policy(diagnostic_command, allow("s3:GetObject", [diagnostics, receipts]))},
            },
            "CoordinatorArtifactAccess": {
                "Type": "AWS::IAM::Policy",
                "Properties": {"PolicyName": "JumpServeTrainingOperationArtifacts",
                               "Roles": ["JumpServeSyntheticBatchCoordinator"],
                               "PolicyDocument": policy(allow("s3:GetObject", archives),
                                                        allow("s3:PutObject", [receipts, diagnostics]))},
            },
        },
        "Outputs": {
            "ReleaseRoleArn": {"Value": {"Fn::GetAtt": ["GithubReleaseRole", "Arn"]}},
            "ReleaseDocumentName": {"Value": ref("ReleaseDocument")},
            "DiagnosticsDocumentName": {"Value": ref("DiagnosticsDocument")},
        },
    }


if __name__ == "__main__":
    print(json.dumps(template(), indent=2))
