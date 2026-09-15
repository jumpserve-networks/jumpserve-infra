import { CloudWatchLogsClient, GetLogEventsCommand } from '@aws-sdk/client-cloudwatch-logs';
import { handler } from '../lambda/get-benchmark-logs';

afterEach(() => jest.restoreAllMocks());

test('polling without a cursor requests the latest log entries', async () => {
  const send = jest.spyOn(CloudWatchLogsClient.prototype, 'send').mockResolvedValue({
    events: [{ timestamp: 1234, message: 'Benchmark phase: running' }],
    nextForwardToken: 'forward-token',
  } as never);
  const result = await handler({ queryStringParameters: { jobId: 'job-test' } });
  expect(result.statusCode).toBe(200);
  const request = send.mock.calls[0][0] as GetLogEventsCommand;
  expect(request.input).toEqual({
    logGroupName: '/jumpserve/benchmark', logStreamName: 'job-test',
    startFromHead: false, limit: 200,
  });
  expect(JSON.parse(result.body)).toEqual({
    events: [{ timestamp: 1234, message: 'Benchmark phase: running' }], nextToken: 'forward-token',
  });
});

test('forward pagination passes the AWS nextToken request field', async () => {
  const send = jest.spyOn(CloudWatchLogsClient.prototype, 'send').mockResolvedValue({ events: [] } as never);
  await handler({ queryStringParameters: { jobId: 'job-test', nextToken: 'forward-token' } });
  const request = send.mock.calls[0][0] as GetLogEventsCommand;
  expect(request.input.nextToken).toBe('forward-token');
  expect(request.input.startFromHead).toBe(true);
  expect(request.input).not.toHaveProperty('nextForwardToken');
});

test('historical log responses redact credential tokens and preserve diagnostics', async () => {
  const syntheticJwt = 'eyJhbGciOiJIUzI1NiJ9.syntheticPayload.syntheticSignature';
  const syntheticSecret = 'sb_secret_syntheticTestCredential';
  jest.spyOn(CloudWatchLogsClient.prototype, 'send').mockResolvedValue({ events: [
    { timestamp: 1, message: `+ --supabase-service-role-key ${syntheticJwt}` },
    { timestamp: 2, message: `Authorization: Bearer ${syntheticJwt}` },
    { timestamp: 3, message: `apikey: ${syntheticSecret}` },
    { timestamp: 4, message: 'Benchmark failed during running (exit 2)' },
  ] } as never);
  const result = await handler({ queryStringParameters: { jobId: 'old-job' } });
  expect(result.body).not.toContain(syntheticJwt);
  expect(result.body).not.toContain(syntheticSecret);
  const { events } = JSON.parse(result.body);
  expect(events[0].message).toBe('+ --supabase-service-role-key [REDACTED]');
  expect(events[1].message).toBe('Authorization: Bearer [REDACTED]');
  expect(events[2].message).toBe('apikey: [REDACTED]');
  expect(events[3].message).toBe('Benchmark failed during running (exit 2)');
});
