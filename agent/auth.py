"""Verify request identity before reading chat history or invoking Bedrock."""
import os
import httpx


class AuthError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def authenticate(event):
    headers = {key.lower(): value for key, value in (event.get('headers') or {}).items()}
    bearer = headers.get('authorization', '')
    if not bearer.startswith('Bearer ') or len(bearer.split()) != 2 or len(bearer) > 8192:
        raise AuthError(401, 'Sign in to chat with the AI.')
    try:
        response = httpx.get(os.environ['SUPABASE_URL'] + '/auth/v1/user',
            headers={'Authorization': bearer, 'apikey': os.environ['SUPABASE_ANON_KEY']}, timeout=8)
        if response.status_code in (401, 403):
            raise AuthError(401, 'Your session has expired. Sign in again.')
        response.raise_for_status()
        user = response.json()
    except AuthError:
        raise
    except Exception as error:
        raise AuthError(503, 'Authentication is temporarily unavailable. Please try again.') from error
    if user.get('is_anonymous') or not user.get('id') or not any(i.get('provider') == 'google' for i in user.get('identities', [])):
        raise AuthError(403, 'Google authentication is required.')
    return user, bearer
