import {
  CloudWatchLogsClient,
  GetLogEventsCommand,
} from '@aws-sdk/client-cloudwatch-logs';

const cwl = new CloudWatchLogsClient({});

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

    const params: any = {
      logGroupName: '/jumpserve/benchmark',
      logStreamName: jobId,
      startFromHead: true,
      limit: 200,
    };

    if (nextToken) {
      params.nextForwardToken = nextToken;
    }

    const result = await cwl.send(new GetLogEventsCommand(params));

    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({
        events: (result.events || []).map(e => ({
          timestamp: e.timestamp,
          message: e.message,
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
