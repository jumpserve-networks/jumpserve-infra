import * as cdk from 'aws-cdk-lib/core';
import * as amplify from 'aws-cdk-lib/aws-amplify';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export class AmplifyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const githubToken = secretsmanager.Secret.fromSecretNameV2(
      this, 'GitHubToken', 'jumpserve/github-token'
    );

    const supabaseUrl = this.node.tryGetContext('supabaseUrl');
    const supabaseAnonKey = this.node.tryGetContext('supabaseAnonKey');
    const frontendRepo = this.node.tryGetContext('frontendRepo') || 'BradleyFang/jumpserve-front-end';

    const amplifyApp = new amplify.CfnApp(this, 'JumpServeFrontend', {
      name: 'jumpserve-frontend',
      repository: `https://github.com/${frontendRepo}`,
      accessToken: githubToken.secretValue.unsafeUnwrap(),
      platform: 'WEB_COMPUTE',
      environmentVariables: [
        { name: 'NEXT_PUBLIC_SUPABASE_URL', value: supabaseUrl },
        { name: 'NEXT_PUBLIC_SUPABASE_ANON_KEY', value: supabaseAnonKey },
        { name: 'NEXT_PUBLIC_BENCHMARK_API_URL', value: this.node.tryGetContext('benchmarkApiUrl') || '' },
        { name: 'NEXT_PUBLIC_AGENT_URL', value: this.node.tryGetContext('agentUrl') || '' },
      ],
      buildSpec: JSON.stringify({
        version: 1,
        frontend: {
          phases: {
            preBuild: { commands: ['npm ci'] },
            build: { commands: ['npm run build'] },
          },
          artifacts: {
            baseDirectory: '.next',
            files: ['**/*'],
          },
          cache: {
            paths: ['node_modules/**/*'],
          },
        },
      }),
    });

    const mainBranch = new amplify.CfnBranch(this, 'MainBranch', {
      appId: amplifyApp.attrAppId,
      branchName: 'main',
      enableAutoBuild: true,
      stage: 'PRODUCTION',
    });

    const customDomain = this.node.tryGetContext('customDomain');
    if (customDomain) {
      const domain = new amplify.CfnDomain(this, 'CustomDomain', {
        appId: amplifyApp.attrAppId,
        domainName: customDomain,
        subDomainSettings: [
          {
            branchName: mainBranch.branchName,
            prefix: '',
          },
        ],
      });

      new cdk.CfnOutput(this, 'CustomDomainUrl', {
        value: `https://${customDomain}`,
        description: 'Custom domain URL',
      });
    }

    new cdk.CfnOutput(this, 'AmplifyAppId', {
      value: amplifyApp.attrAppId,
      description: 'Amplify App ID',
    });

    new cdk.CfnOutput(this, 'AmplifyDefaultDomain', {
      value: `https://main.${amplifyApp.attrDefaultDomain}`,
      description: 'Amplify default domain URL',
    });
  }
}
