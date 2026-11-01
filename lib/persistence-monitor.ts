import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import {Construct} from 'constructs';
import * as path from 'path';

/** Separate from both worker host and Supabase; failures retain an AWS incident. */
export class PersistenceMonitor extends Construct {
  constructor(scope: Construct, id: string) {
    super(scope, id);
    const stack = cdk.Stack.of(this);
    if (stack.account !== '395567831870' || stack.region !== 'us-east-1') {
      throw new Error('Fixed JumpServe monitoring account and region required.');
    }
    const secret = secrets.Secret.fromSecretNameV2(this, 'ServiceKey', 'jumpserve/supabase-service-key');
    const group = new logs.LogGroup(this, 'Logs', {retention: logs.RetentionDays.ONE_MONTH});
    const role = new iam.Role(this, 'Role', {assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com')});
    group.grantWrite(role);
    const probe = new lambda.Function(this, 'Probe', {
      role,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'monitor.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'assets', 'persistence-monitor'), {
        exclude: ['__pycache__', '*.pyc'],
      }),
      timeout: cdk.Duration.seconds(20),
      memorySize: 128,
      reservedConcurrentExecutions: 1,
      retryAttempts: 0,
      maxEventAge: cdk.Duration.minutes(1),
      logGroup: group,
      environment: {SUPABASE_SECRET_ARN: secret.secretArn},
    });
    secret.grantRead(probe);
    probe.addToRolePolicy(new iam.PolicyStatement({
      actions: ['cloudwatch:PutMetricData'], resources: ['*'],
      conditions: {StringEquals: {'cloudwatch:namespace': 'JumpServe/Persistence'}},
    }));
    new events.Rule(this, 'EveryMinute', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(1)),
      targets: [new targets.LambdaFunction(probe, {retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1)})],
    });
    const metric = (name: string, statistic: string) => new cloudwatch.Metric({
      namespace: 'JumpServe/Persistence', metricName: name,
      dimensionsMap: {Project: 'regphejnlvfpyokpniny'},
      period: cdk.Duration.minutes(1), statistic,
    });
    const reachable = metric('DatabaseReachable', 'Minimum');
    const latency = metric('DatabaseLatencyMs', 'Maximum');
    const unavailable = new cloudwatch.Alarm(this, 'Unavailable', {
      alarmName: 'JumpServe-Supabase-Unavailable', metric: reachable,
      comparisonOperator: cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      threshold: 1, evaluationPeriods: 3, datapointsToAlarm: 3,
      treatMissingData: cloudwatch.TreatMissingData.BREACHING,
      alarmDescription: 'Three failed or missing minute probes. Check Supabase health and retained worker evidence; no automatic restart or inference replay.',
    });
    const slow = new cloudwatch.Alarm(this, 'Slow', {
      alarmName: 'JumpServe-Supabase-Slow', metric: latency,
      threshold: 2000, evaluationPeriods: 5, datapointsToAlarm: 3,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      alarmDescription: 'Persistence probe exceeds two seconds in three of five minutes. Inspect disk I/O, memory and query pressure.',
    });
    unavailable.addAlarmAction(new actions.SsmAction(actions.OpsItemSeverity.CRITICAL, actions.OpsItemCategory.AVAILABILITY));
    slow.addAlarmAction(new actions.SsmAction(actions.OpsItemSeverity.MEDIUM, actions.OpsItemCategory.PERFORMANCE));
    const dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {dashboardName: 'JumpServe-Persistence'});
    dashboard.addWidgets(new cloudwatch.AlarmStatusWidget({title: 'Persistence incidents', alarms: [unavailable, slow], width: 24}));
    dashboard.addWidgets(new cloudwatch.GraphWidget({title: 'Database reachable (1 = verified read)', left: [reachable]}),
      new cloudwatch.GraphWidget({title: 'Database read latency (ms)', left: [latency]}));
    new cdk.CfnOutput(stack, 'PersistenceDashboardUrl', {
      value: `https://${stack.region}.console.aws.amazon.com/cloudwatch/home?region=${stack.region}#dashboards:name=JumpServe-Persistence`,
    });
    new cdk.CfnOutput(stack, 'PersistenceProbeFunction', {value: probe.functionName});
  }
}
