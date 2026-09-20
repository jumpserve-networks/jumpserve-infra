"""Server-side Supabase access shared by prompt loading and session persistence."""
import os

import boto3
import httpx

_service_key = None


class Database:
    def __init__(self, url=None):
        self.url = (url or os.environ.get('SUPABASE_URL', '')).rstrip('/')
        if not self.url.startswith('https://'):
            raise ValueError('SUPABASE_URL must be an HTTPS URL')

    def headers(self):
        global _service_key
        if not _service_key:
            _service_key = boto3.client('secretsmanager', region_name='us-east-1').get_secret_value(
                SecretId=os.environ.get('SUPABASE_SECRET_ARN', 'jumpserve/supabase-service-key')
            )['SecretString']
        return {'apikey': _service_key, 'Authorization': f'Bearer {_service_key}'}

    def get(self, path, params=None):
        response = httpx.get(f'{self.url}/rest/v1/{path}', params=params, headers=self.headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def rpc(self, name, payload):
        response = httpx.post(f'{self.url}/rest/v1/rpc/{name}', json=payload, headers=self.headers(), timeout=15)
        response.raise_for_status()
        return response.json()
