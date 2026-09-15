import {
  CloudWatchLogsClient,
  GetLogEventsCommand,
  type GetLogEventsCommandInput,
} from '@aws-sdk/client-cloudwatch-logs';

const cwl = new CloudWatchLogsClient({});

// Older bootstraps used shell tracing. Avoid redisplaying their credentials
// when the viewer requests the latest part of those historical log streams.
function redactCredentials(message: string | undefined): string {
  return (message || '')
    .replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g, '[REDACTED]')
    .replace(/\bsb_secret_[A-Za-z0-9_-]+\b/g, '[REDACTED]');
}

export const handler = async (event: any) => {
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET,OPTIONS',
  };

  if (event.requestContext?.http?.method === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders, body: '' };
  }

  try {
    const jobId = event.queryStringParameters?.jobId;
    const nextToken = event.queryStringParameters?.nextToken;

    if (!jobId) {
      return {
        statusCode: 400,
        headers: corsHeaders,
        body: JSON.stringify({ error: 'jobId query parameter is required' }),
      };
    }

    const params: GetLogEventsCommandInput = {
      logGroupName: '/jumpserve/benchmark',
      logStreamName: jobId,
      // The UI polls without a token: show recent output, not the same first
      // 200 package-installation events forever. Forward cursors require true.
      startFromHead: Boolean(nextToken),
      limit: 200,
    };

    if (nextToken) {
      params.nextToken = nextToken;
    }

    const result = await cwl.send(new GetLogEventsCommand(params));

    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({
        events: (result.events || []).map(e => ({
          timestamp: e.timestamp,
          message: redactCredentials(e.message),
        })),
        nextToken: result.nextForwardToken,
      }),
    };
  } catch (err: any) {
    if (err.name === 'ResourceNotFoundException') {
      return {
        statusCode: 200,
        headers: corsHeaders,
        body: JSON.stringify({ events: [], nextToken: null }),
      };
    }
    console.error('Error fetching logs:', err);
    return {
      statusCode: 500,
      headers: corsHeaders,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
