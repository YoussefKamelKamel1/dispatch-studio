"""Read-only AI connection checks. Never return credentials or provider response bodies."""
from urllib.parse import quote

import httpx

from .core import now


def ai_connection(settings, check=None):
    return {'provider': 'OpenAI', 'mode': settings.mode, 'model': settings.model,
            'key_configured': bool(settings.api_key.strip()),
            'status': 'demo' if settings.mode == 'demo' else 'configured' if settings.api_key.strip() else 'needs_key',
            'check': check}


def check_ai(settings, client=None):
    result = {'checked_at': now()}
    if not settings.api_key.strip():
        return result | {'status': 'needs_key', 'detail': 'Add OPENAI_API_KEY to the server .env file, then restart.'}
    if client is None:
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as owned:
                return check_ai(settings, owned)
        except Exception:
            return result | {'status': 'failed', 'detail': 'OpenAI could not be reached. Check the server connection.'}
    response = client.get('https://api.openai.com/v1/models/' + quote(settings.model, safe=''),
                          headers={'Authorization': 'Bearer ' + settings.api_key})
    if response.status_code == 200:
        return result | {'status': 'verified', 'detail': 'API key and model access verified. Generation and available quota still need a live request.'}
    detail = {401: 'The API key was rejected.', 403: 'This key does not have access to the model.',
              404: 'The configured model was not found or is unavailable to this key.',
              429: 'The provider rate limit was reached. Try again later.'}.get(response.status_code,
                  f'OpenAI returned HTTP {response.status_code}. Check the account and configuration.')
    return result | {'status': 'failed', 'detail': detail}
